from sema4ai.actions import Response, action
from robocorp import browser
import dotenv
import os
import time
from typing import Dict, Any, Optional
from datetime import datetime

from ..utils.db import (
    read_job_by_id,
    update_is_applied,
    get_jobs_by_run_id
)
from ..utils.enriched_answers import (
    get_enriched_answers,
    mark_answers_used,
)
from ..utils.apply_tools import _ensure_logged_in
from ..utils.tools import configure_browser, _load_profile
from ..utils.robolog import setup_logging, log, cleanup_logging
from ..utils.robolog_screenshots import (
    log_section_start, log_section_end,
    log_success, log_warning, log_error,
    log_metric, capture_screenshot
)

dotenv.load_dotenv()


# _load_profile is now imported from tools.py


@action
def apply_to_single_job(
    job_id: str,
    headless: bool = True,
    allow_submit: bool = False
) -> Response:
    """Apply to a single LinkedIn Easy Apply job using data from database.
    
    Queries the database for job details, profile, and AI-generated answers,
    then automates the Easy Apply process.
    
    Args:
        job_id: LinkedIn job ID to apply to (from database)
        headless: Run browser in headless mode (default: True)
        allow_submit: Actually submit application (default: False for safety)
    
    Returns:
        Response with application result
    """
    # Setup logging
    run_id = f"apply_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    setup_logging(
        output_dir=f"./output/{run_id}",
        enable_html_report=True,
        log_level="info"
    )
    
    try:
        log_section_start(f"Job Application: {job_id}", "📝")
        log.info(f"Job ID: {job_id}")
        log.info(f"Headless mode: {headless}")
        log.info(f"Submit mode: {'ENABLED' if allow_submit else 'DRY RUN'}")
        
        # Get job from database
        job = read_job_by_id(job_id)
        if not job:
            log_error(
                "Job not found in database",
                details=f"Job ID: {job_id}",
                screenshot=False
            )
            return Response(result={
                "success": False,
                "error": f"Job {job_id} not found in database",
                "job_id": job_id,
                "log_file": f"./output/{run_id}/log.html"
            })
        
        # Check if Easy Apply job
        if not job.get('easy_apply'):
            log_error(
                "Job is not an Easy Apply job",
                details=f"Job: {job.get('title')} at {job.get('company')}",
                screenshot=False
            )
            return Response(result={
                "success": False,
                "error": "Job is not an Easy Apply job",
                "job_id": job_id,
                "log_file": f"./output/{run_id}/log.html"
            })
        
        # Check if job is a good fit (if fit analysis was done)
        if job.get('good_fit') is False:
            fit_score = job.get('fit_score', 0.0)
            log_warning(
                "Job marked as bad fit",
                details=f"{job.get('title')} at {job.get('company')} - Fit score: {fit_score:.2f}",
                screenshot=False
            )
            return Response(result={
                "success": False,
                "error": f"Job is not a good fit for your profile (fit_score: {fit_score:.2f})",
                "job_id": job_id,
                "job_title": job.get('title'),
                "company": job.get('company'),
                "good_fit": False,
                "fit_score": fit_score,
                "log_file": f"./output/{run_id}/log.html"
            })
        
        # Get job URL
        job_url = job.get('job_url')
        if not job_url:
            log_error(
                "Job URL not found",
                details=f"Job {job_id} has no job_url in database",
                screenshot=False
            )
            return Response(result={
                "success": False,
                "error": "Job URL not found",
                "job_id": job_id,
                "log_file": f"./output/{run_id}/log.html"
            })
        
        # Load profile
        profile = _load_profile()
        if not profile:
            log_error(
                "No user profile found",
                details="Run parse_resume_and_save_profile() first",
                screenshot=False
            )
            return Response(result={
                "success": False,
                "error": "No user profile found. Run parse_resume_and_save_profile() first.",
                "job_id": job_id,
                "log_file": f"./output/{run_id}/log.html"
            })
        
        # Get answers from enriched_answers table
        enriched = get_enriched_answers(job_id)
        answers = {}
        
        if enriched and enriched.get('answers'):
            answers = enriched['answers']
            confidence = enriched.get('confidence_score', 0.0)
            log.info(f"Using enriched answers ({len(answers)} fields, confidence: {confidence:.2f})")
        else:
            log.info("No enriched answers found, will use profile auto-fill")
        
        log.info("Configuring browser and ensuring login...")
        # Configure browser
        configure_browser(headless_mode=headless)
        page = browser.page()
        _ensure_logged_in(page)
        
        # Use core apply function (single source of truth)
        from ..utils.apply_core import _apply_to_job_core
        
        log.info(f"Starting application process for: {job.get('title')} at {job.get('company')}")
        apply_result = _apply_to_job_core(
            page=page,
            job_id=job_id,
            job_url=job_url,
            job_title=job.get('title', 'Unknown'),
            company=job.get('company', 'Unknown'),
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
                    details=f"{job.get('title')} at {job.get('company')}",
                    screenshot=True,
                    screenshot_name="application_submitted"
                )
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
        
        # Mark enriched answers as used if successfully submitted
        if apply_result.get("submitted") and enriched:
            mark_answers_used(job_id)
            log.info(f"Marked enriched answers as used for job {job_id}")
        
        # Update is_applied status if actually submitted (not dry-run)
        if apply_result.get("submitted") and allow_submit:
            update_is_applied(job_id, is_applied=True)
            log.info(f"Marked job {job_id} as applied in database")
        
        # Verification if submitted
        verification_message = None
        if apply_result.get("submitted") and allow_submit:
            log.info("Verifying submission...")
            try:
                page.goto("https://www.linkedin.com/my-items/saved-jobs/?cardType=APPLIED", timeout=30000)
                time.sleep(2)
                
                page_content = page.content()
                if job_id in page_content:
                    apply_result["verified"] = True
                    verification_message = f"Verified: Job {job_id} on Applied Jobs page"
                    log.info(f"✅ {verification_message}")
                else:
                    verification_message = f"Job {job_id} not yet visible (may take time)"
                    log.warn(f"⚠️ {verification_message}")
            except Exception as e:
                verification_message = f"Could not verify: {e}"
                log.warn(f"⚠️ {verification_message}")
        
        # Keep browser open briefly if dry-run
        if not allow_submit and apply_result.get("success"):
            log.info("Dry-run complete. Browser stays open 2 seconds...")
            time.sleep(2)
        
        log_section_end("Job Application", "✅" if apply_result.get("success") else "❌")
        page.close()
        
        return Response(result={
            "success": apply_result.get("success"),
            "job_id": job_id,
            "job_title": job.get('title'),
            "company": job.get('company'),
            "submitted": apply_result.get("submitted"),
            "verified": apply_result.get("verified"),
            "verification_message": verification_message,
            "allow_submit": allow_submit,
            "steps_completed": apply_result.get("steps_completed"),
            "fields_filled": apply_result.get("fields_filled"),
            "reached_submit": apply_result.get("reached_submit"),
            "used_enriched_answers": enriched is not None,
            "error": apply_result.get("error"),
            "log_file": f"./output/{run_id}/log.html"
        })
    
    except Exception as e:
        log_error(
            "Application failed with unexpected error",
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
            "job_id": job_id,
            "log_file": f"./output/{run_id}/log.html"
        })
    
    finally:
        cleanup_logging()


@action
def batch_apply_by_run_id(
    run_id: str,
    headless: bool = True,
    allow_submit: bool = False,
    max_applications: int = 10
) -> Response:
    """Batch apply to Easy Apply jobs from a search run. Queries database and automatically applies to each job using AI-generated answers.
    
    Args:
        run_id: The search run ID from search_linkedin_easy_apply()
        headless: Run browser in headless mode (default: True)
        allow_submit: Actually submit applications (default: False for safety)
        max_applications: Maximum number of jobs to apply to (default: 10)
    
    Returns:
        Response with application summary (applied/skipped/failed counts)
    """
    try:
        print(f"[ACTION] Starting batch apply for run_id: {run_id}")
        print(f"[ACTION] Submit mode: {'ENABLED' if allow_submit else 'DRY RUN (disabled)'}")
        
        # Get all Easy Apply jobs from this run
        jobs = get_jobs_by_run_id(run_id)
        easy_apply_jobs = [j for j in jobs if j.get('easy_apply')]
        
        # Filter jobs that are good fits (if fit analysis was done)
        good_fit_jobs = []
        for job in easy_apply_jobs:
            # Check good_fit flag if it exists
            if job.get('good_fit') is False:
                print(f"[Filter] Skipping {job.get('job_id')} - bad fit (score: {job.get('fit_score', 0):.2f})")
                continue
            good_fit_jobs.append(job)
        
        print(f"[Filter] {len(good_fit_jobs)}/{len(easy_apply_jobs)} jobs passed fit check")
        
        # Filter jobs that have enriched answers
        jobs_with_answers = []
        for job in good_fit_jobs:
            job_id = job.get('job_id')
            if job_id:
                enriched = get_enriched_answers(job_id)
                if enriched and enriched.get('answers'):
                    jobs_with_answers.append(job)
        
        print(f"[ACTION] Found {len(jobs_with_answers)} Easy Apply jobs with enriched answers")
        
        if not jobs_with_answers:
            return Response(result={
                "success": False,
                "message": "No Easy Apply jobs with enriched answers found. Run generate_answers_for_run() first.",
                "run_id": run_id,
                "applied": 0,
                "skipped": 0,
                "failed": 0
            })
        
        # Sort jobs by priority: recency + fit score
        # Priority: good_fit first, then by date_posted (newest first), then by fit_score
        from datetime import datetime
        
        def sort_priority(job):
            # Good fit gets highest priority
            good_fit = 1 if job.get('good_fit') else 0
            
            # Parse date_posted for recency scoring
            date_posted = job.get('date_posted')
            recency_score = 0
            if date_posted:
                try:
                    posted_dt = datetime.fromisoformat(date_posted.replace('Z', '+00:00'))
                    now = datetime.now(posted_dt.tzinfo) if posted_dt.tzinfo else datetime.now()
                    days_old = (now - posted_dt).days
                    # Newer jobs get higher score (1.0 for today, decreases with age)
                    recency_score = max(0, 1.0 - (days_old / 30.0))
                except:
                    recency_score = 0
            
            # Fit score (0.0-1.0)
            fit_score = job.get('fit_score', 0.0) or 0.0
            
            # Combined priority: good_fit (0-1) * 100 + recency (0-1) * 10 + fit_score (0-1)
            # This ensures: good_fits first, then recent jobs, then high fit scores
            return -(good_fit * 100 + recency_score * 10 + fit_score)
        
        jobs_with_answers.sort(key=sort_priority)
        print(f"[ACTION] Sorted jobs by priority (good_fit > recency > fit_score)")
        
        # Limit applications
        jobs_to_apply = jobs_with_answers[:max_applications]
        print(f"[ACTION] Will apply to {len(jobs_to_apply)}/{len(jobs_with_answers)} jobs (max_applications={max_applications})")
        
        # Load profile
        profile = _load_profile()
        if not profile:
            return Response(result={
                "success": False,
                "error": "No user profile found. Run parse_resume_and_save_profile() first.",
                "run_id": run_id
            })
        
        # Configure browser ONCE for all applications
        configure_browser(headless_mode=headless)
        page = browser.page()
        _ensure_logged_in(page)
        
        applied = 0
        skipped = 0
        failed = 0
        results = []
        
        # Use core apply function for each job (single source of truth)
        from ..utils.apply_core import _apply_to_job_core
        
        for job in jobs_to_apply:
            job_id = job.get('job_id')
            job_url = job.get('job_url')
            job_title = job.get('title', 'Unknown')
            company = job.get('company', 'Unknown')
            
            # Type guards
            if not job_url or not job_id:
                print(f"[ACTION] Missing job_url or job_id, skipping")
                skipped += 1
                continue
            
            print(f"\n[ACTION] === Applying to: {job_title} at {company} ({job_id}) ===")
            
            try:
                # Get enriched answers
                enriched = get_enriched_answers(job_id)
                if not enriched or not enriched.get('answers'):
                    print(f"[ACTION] No enriched answers found for job {job_id}, skipping")
                    skipped += 1
                    results.append({
                        "job_id": job_id,
                        "title": job_title,
                        "company": company,
                        "status": "skipped",
                        "reason": "No enriched answers"
                    })
                    continue
                
                answers = enriched['answers']
                print(f"[ACTION] Using enriched answers (confidence: {enriched.get('confidence_score', 0):.2f})")
                
                # Apply using core function (single source of truth)
                apply_result = _apply_to_job_core(
                    page=page,
                    job_id=job_id,
                    job_url=job_url,
                    job_title=job_title,
                    company=company,
                    profile=profile,
                    answers=answers,
                    allow_submit=allow_submit
                )
                
                # Process result
                if apply_result.get("success"):
                    applied += 1
                    
                    # Mark answers as used if submitted
                    if apply_result.get("submitted"):
                        mark_answers_used(job_id)
                        
                        # Update is_applied status if actually submitted (not dry-run)
                        if allow_submit:
                            update_is_applied(job_id, is_applied=True)
                            print(f"[ACTION] Marked job {job_id} as applied in database")
                    
                    results.append({
                        "job_id": job_id,
                        "title": job_title,
                        "company": company,
                        "status": "applied" if apply_result.get("submitted") else "dry_run",
                        "submitted": apply_result.get("submitted"),
                        "steps": apply_result.get("steps_completed"),
                        "fields_filled": apply_result.get("fields_filled")
                    })
                    print(f"[ACTION] {'✓ Submitted' if apply_result.get('submitted') else 'Dry-run completed'}")
                else:
                    failed += 1
                    results.append({
                        "job_id": job_id,
                        "title": job_title,
                        "company": company,
                        "status": "failed",
                        "error": apply_result.get("error")
                    })
                    print(f"[ACTION] ✗ Failed: {apply_result.get('error')}")
                
                # Short delay between applications
                time.sleep(1.5)
                
            except Exception as e:
                print(f"[ACTION] Exception applying to job {job_id}: {e}")
                failed += 1
                results.append({
                    "job_id": job_id,
                    "title": job_title,
                    "company": company,
                    "status": "failed",
                    "error": str(e)
                })
                continue
        
        # Close browser
        try:
            browser.playwright().stop()
        except:
            pass
        
        return Response(result={
            "success": True,
            "message": f"Batch apply complete: {applied} applied, {skipped} skipped, {failed} failed",
            "run_id": run_id,
            "total_jobs": len(jobs_to_apply),
            "applied": applied,
            "skipped": skipped,
            "failed": failed,
            "submitted": allow_submit,
            "results": results
        })
        
    except Exception as e:
        print(f"[ACTION] Error in batch_apply_by_run_id: {e}")
        import traceback
        print(f"[ACTION] Full traceback: {traceback.format_exc()}")
        
        # Try to close browser on error
        try:
            browser.playwright().stop()
        except:
            pass
        
        return Response(result={
            "success": False,
            "error": str(e),
            "run_id": run_id,
            "applied": 0,
            "skipped": 0,
            "failed": 0
        })
