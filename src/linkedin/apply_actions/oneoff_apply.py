"""
One-off job application action.

Directly navigates to a LinkedIn job URL/ID, scrapes the Easy Apply form,
generates answers with LLM, and applies immediately.
"""
from sema4ai.actions import Response, action
from robocorp import browser
import dotenv
import os
import json
import time
from typing import Dict, Any, Optional
from datetime import datetime

from ..utils.db import (
    get_active_profile,
    write_jobs,
    update_is_applied
)
from ..utils.apply_tools import _ensure_logged_in
from ..utils.tools import (
    configure_browser,
    _open_easy_apply_and_snapshot
)
from ..utils.openai_client import generate_answers
from ..utils.robolog import setup_logging, cleanup_logging, get_logger
from ..utils.robolog_screenshots import (
    log_section_start, log_section_end,
    log_success, log_warning, log_error,
    log_metric
)

# Initialize logger
log = get_logger(__name__)

dotenv.load_dotenv()


def _extract_job_id_from_url(job_url: str) -> Optional[str]:
    """Extract job ID from LinkedIn job URL.
    
    Args:
        job_url: Full LinkedIn job URL or just the job ID
    
    Returns:
        Job ID string or None if not found
    """
    # If it's already just an ID (numeric string)
    if job_url.isdigit():
        return job_url
    
    # Try to extract from URL
    import re
    match = re.search(r'/jobs/view/(\d+)', job_url)
    if match:
        return match.group(1)
    
    # Try alternative pattern
    match = re.search(r'currentJobId=(\d+)', job_url)
    if match:
        return match.group(1)
    
    return None


def _scrape_job_details_from_page(page, job_id: str) -> Dict[str, Any]:
    """Scrape basic job details from the current job page.
    
    Args:
        page: Playwright page object
        job_id: Job ID string
    
    Returns:
        Dictionary with job details
    """
    try:
        # Wait for job details to load
        time.sleep(1.5)
        
        # Use the reusable extraction tools with context='detail'
        from linkedin.utils.tools import (
            extract_job_title,
            extract_company_name,
            extract_location_data,
            extract_job_description,
            extract_compensation_data,
            extract_job_metadata
        )
        
        # Extract all fields using the unified tools
        title = extract_job_title(page, context='detail')
        company = extract_company_name(page, context='detail', existing_title=title)
        location = extract_location_data(page, context='detail')
        description = extract_job_description(page, context='detail')
        compensation = extract_compensation_data(page, context='detail')
        metadata = extract_job_metadata(page, context='detail')
        
        return {
            "job_id": job_id,
            "title": title,
            "company": company,
            "location_raw": location["raw_location"],
            "location_city": location["city"],
            "location_state": location["state"],
            "location_country": location["country"],
            "location_type": location["location_type"],
            "job_description": description,
            "salary_range": compensation["salary_range"],
            "compensation_raw": compensation["raw_compensation"],
            "benefits": compensation["benefits"],
            "date_posted": metadata["date_posted"],
            "job_type": metadata["job_type"],
            "verified_company": metadata["verified_company"],
            "job_url": page.url,
            "easy_apply": True,  # Assumed if we got here
            "scraped_at": datetime.now().isoformat(),
        }
    
    except Exception as e:
        log.warn(f"Error scraping job details: {e}")
        return {
            "job_id": job_id,
            "title": "Unknown Title",
            "company": "Unknown Company",
            "job_url": page.url,
            "easy_apply": True,
            "scraped_at": datetime.now().isoformat(),
        }


@action
def apply_to_job_by_url(
    job_url: str,
    headless: bool = True,
    allow_submit: bool = False
) -> Response:
    """Apply to a LinkedIn job directly by URL/ID with dynamic form scraping.
    
    This action:
    1. Navigates directly to the job page
    2. Checks if Easy Apply is available (gracefully exits if not)
    3. Dynamically scrapes the Easy Apply form
    4. Generates answers using LLM and user profile
    5. Applies immediately
    6. Saves job to database (even if Easy Apply fails)
    
    Args:
        job_url: LinkedIn job URL (e.g., "https://www.linkedin.com/jobs/view/1234567890") or just the job ID
        headless: Run browser in headless mode (default: True)
        allow_submit: Actually submit application (default: False for safety)
    
    Returns:
        Response with application result
    """
    # Setup logging
    run_id = f"oneoff_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    setup_logging(
        output_dir=f"./output/{run_id}",
        enable_html_report=True,
        log_level="info"
    )
    
    try:
        log_section_start("One-off Job Application", "🎯")
        log.info(f"Job URL/ID: {job_url}")
        log.info(f"Headless mode: {headless}")
        log.info(f"Submit mode: {'ENABLED' if allow_submit else 'DRY RUN'}")
        
        # Extract job ID from URL
        job_id = _extract_job_id_from_url(job_url)
        if not job_id:
            log_error(
                "Could not extract job ID from URL",
                details=f"Provided: {job_url}",
                screenshot=False
            )
            return Response(result={
                "success": False,
                "error": f"Could not extract job ID from: {job_url}",
                "log_file": f"./output/{run_id}/log.html"
            })
        
        log.info(f"Extracted job ID: {job_id}")
        
        # Load profile
        profile = get_active_profile()
        if not profile:
            log_error(
                "No user profile found",
                details="Run parse_resume_and_save_profile() first",
                screenshot=False
            )
            return Response(result={
                "success": False,
                "error": "No user profile found. Run parse_resume_and_save_profile() first.",
                "log_file": f"./output/{run_id}/log.html"
            })
        
        log.info("Configuring browser and ensuring login...")
        # Configure browser
        configure_browser(headless_mode=headless)
        page = browser.page()
        _ensure_logged_in(page)
        
        # Navigate to job page
        full_job_url = job_url if job_url.startswith('http') else f"https://www.linkedin.com/jobs/view/{job_id}"
        log.info(f"Navigating to job page: {full_job_url}")
        
        try:
            page.goto(full_job_url, timeout=30000, wait_until="domcontentloaded")
            time.sleep(2)  # Wait for dynamic content
        except Exception as e:
            log_error(
                "Failed to navigate to job page",
                details=str(e),
                screenshot=True,
                screenshot_name="navigation_failed"
            )
            return Response(result={
                "success": False,
                "error": f"Failed to navigate to job page: {e}",
                "job_id": job_id,
                "log_file": f"./output/{run_id}/log.html"
            })
        
        # Scrape basic job details first (for database)
        log.info("Scraping job details...")
        job_data = _scrape_job_details_from_page(page, job_id)
        log.info(f"Job: {job_data.get('title')} at {job_data.get('company')}")
        
        # Scrape Easy Apply form (this function handles clicking the button and checking if it exists)
        log.info("Opening Easy Apply and scraping form...")
        try:
            form_snapshot = _open_easy_apply_and_snapshot(page)
            
            if not form_snapshot:
                # form_snapshot being None means Easy Apply button was not found
                log_warning(
                    "Job does not have Easy Apply button",
                    details="Could not find or click Easy Apply button",
                    screenshot=True,
                    screenshot_name="no_easy_apply"
                )
                
                # Save job to database without Easy Apply
                job_data["easy_apply"] = False
                job_data["run_id"] = run_id
                try:
                    write_jobs([job_data])
                except Exception as e:
                    log.warn(f"Could not save job to database: {e}")
                
                return Response(result={
                    "success": False,
                    "error": "Job does not have Easy Apply",
                    "job_id": job_id,
                    "job_title": job_data.get("title"),
                    "company": job_data.get("company"),
                    "easy_apply": False,
                    "log_file": f"./output/{run_id}/log.html"
                })
            
            if not form_snapshot.get('questions_json'):
                log_error(
                    "Easy Apply form opened but no questions found",
                    details="Form may have loaded incorrectly",
                    screenshot=True,
                    screenshot_name="form_scrape_failed"
                )
                
                # Still save job to database
                job_data["easy_apply"] = True
                job_data["run_id"] = run_id
                try:
                    write_jobs([job_data])
                except Exception as e:
                    log.warn(f"Could not save job to database: {e}")
                
                return Response(result={
                    "success": False,
                    "error": "Easy Apply form opened but no questions found",
                    "job_id": job_id,
                    "job_title": job_data.get("title"),
                    "company": job_data.get("company"),
                    "easy_apply": True,
                    "log_file": f"./output/{run_id}/log.html"
                })
            
            questions = form_snapshot.get('questions_json', [])
            log_success(f"Scraped {len(questions)} form fields", screenshot=False)
            
            # Update job_data with form snapshot
            job_data["questions_json"] = json.dumps(questions)
            job_data["form_elements"] = json.dumps(form_snapshot.get('form_elements', {}))
            
        except Exception as e:
            log_error(
                "Error scraping Easy Apply form",
                details=str(e),
                screenshot=True,
                screenshot_name="form_scrape_error"
            )
            
            # Still save job to database
            job_data["run_id"] = run_id
            try:
                write_jobs([job_data])
            except Exception as e:
                log.warn(f"Could not save job to database: {e}")
            
            return Response(result={
                "success": False,
                "error": f"Error scraping form: {e}",
                "job_id": job_id,
                "job_title": job_data.get("title"),
                "company": job_data.get("company"),
                "log_file": f"./output/{run_id}/log.html"
            })
        
        # Generate answers with LLM
        log.info("Generating form answers with LLM...")
        try:
            form_answers = generate_answers(
                questions=questions,
                profile=profile,
                job=job_data
            )
            
            if not form_answers or not form_answers.answers:
                log_error(
                    "LLM failed to generate answers",
                    details="No answers returned",
                    screenshot=False
                )
                
                # Save job to database
                job_data["run_id"] = run_id
                try:
                    write_jobs([job_data])
                except Exception as e:
                    log.warn(f"Could not save job to database: {e}")
                
                return Response(result={
                    "success": False,
                    "error": "LLM failed to generate answers",
                    "job_id": job_id,
                    "job_title": job_data.get("title"),
                    "company": job_data.get("company"),
                    "log_file": f"./output/{run_id}/log.html"
                })
            
            answers = form_answers.answers
            confidence = form_answers.confidence or 0.0
            log_metric("Generated Answers", len(answers), "fields", "🤖")
            log_metric("Confidence", f"{confidence:.2%}", "", "📊")
            
            # Update job_data with answers
            job_data["answers_json"] = json.dumps(answers)
            job_data["ai_confidence_score"] = confidence
            
        except Exception as e:
            log_error(
                "Error generating answers",
                details=str(e),
                screenshot=False
            )
            
            # Save job to database
            job_data["run_id"] = run_id
            try:
                write_jobs([job_data])
            except Exception as e:
                log.warn(f"Could not save job to database: {e}")
            
            return Response(result={
                "success": False,
                "error": f"Error generating answers: {e}",
                "job_id": job_id,
                "job_title": job_data.get("title"),
                "company": job_data.get("company"),
                "log_file": f"./output/{run_id}/log.html"
            })
        
        # Save job to database before applying
        job_data["run_id"] = run_id
        job_data["processed"] = True
        try:
            write_jobs([job_data])
            log.info(f"Saved job {job_id} to database with form data and answers")
        except Exception as e:
            log.warn(f"Could not save job to database: {e}")
        
        # Apply to the job using core function
        log.info(f"Applying to job: {job_data.get('title')} at {job_data.get('company')}")
        
        from ..utils.apply_core import _apply_to_job_core
        
        apply_result = _apply_to_job_core(
            page=page,
            job_id=job_id,
            job_url=full_job_url,
            job_title=job_data.get('title', 'Unknown'),
            company=job_data.get('company', 'Unknown'),
            profile=profile,
            answers=answers,
            allow_submit=allow_submit
        )
        
        # Log metrics
        log_metric("Steps Completed", apply_result.get('steps_completed', 0), "steps", "📝")
        log_metric("Fields Filled", apply_result.get('fields_filled', 0), "fields", "✅")
        
        # Check result and log appropriately
        if apply_result.get("success"):
            if apply_result.get("submitted") and allow_submit:
                log_success(
                    "Application submitted successfully!",
                    details=f"{job_data.get('title')} at {job_data.get('company')}",
                    screenshot=True,
                    screenshot_name="application_submitted"
                )
                
                # Update is_applied in database
                try:
                    update_is_applied(job_id, is_applied=True)
                    log.info(f"Marked job {job_id} as applied in database")
                except Exception as e:
                    log.warn(f"Could not update is_applied: {e}")
            else:
                log_success(
                    "Dry-run completed successfully",
                    details="Application filled but not submitted (dry-run mode)",
                    screenshot=False
                )
        else:
            log_error(
                "Application failed",
                details=apply_result.get('error', 'Unknown error'),
                screenshot=True,
                screenshot_name="application_failed"
            )
        
        log_section_end("One-off Application", "✅" if apply_result.get("success") else "❌")
        page.close()
        
        return Response(result={
            "success": apply_result.get("success"),
            "job_id": job_id,
            "job_title": job_data.get('title'),
            "company": job_data.get('company'),
            "submitted": apply_result.get("submitted"),
            "allow_submit": allow_submit,
            "steps_completed": apply_result.get("steps_completed"),
            "fields_filled": apply_result.get("fields_filled"),
            "reached_submit": apply_result.get("reached_submit"),
            "questions_scraped": len(questions),
            "answers_generated": len(answers),
            "confidence": confidence,
            "saved_to_database": True,
            "error": apply_result.get("error"),
            "log_file": f"./output/{run_id}/log.html"
        })
    
    except Exception as e:
        log_error(
            "One-off application failed with unexpected error",
            details=str(e),
            screenshot=True,
            screenshot_name="unexpected_error"
        )
        log.exception()
        
        try:
            browser.playwright().stop()
        except:
            pass
        
        return Response(result={
            "success": False,
            "error": str(e),
            "job_url": job_url,
            "log_file": f"./output/{run_id}/log.html"
        })
    
    finally:
        cleanup_logging()
