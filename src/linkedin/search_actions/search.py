from .filters import _apply_search_filters
from ..utils.search_history import execution_run_id
from actions import ActionError, Response, action
from robocorp import browser
import dotenv
import os
import time
import uuid
import pandas as pd
from typing import List
from datetime import datetime
from pathlib import Path

from ..utils.responses import LinkedInJob, SearchResponse
from ..utils.db import write_jobs, get_jobs_by_run_id
from ..utils.tools import configure_browser, _collect_job_ids_with_pagination, _extract_from_job_page
from ..utils.robolog import setup_logging, log, cleanup_logging
from ..utils.robolog_screenshots import (
    log_section_start, log_section_end,
    log_success, log_warning, log_error,
    log_metric, capture_screenshot, embed_html_table
)

dotenv.load_dotenv()

# Global LinkedIn credentials from environment variables
LINKEDIN_USERNAME = os.getenv("LINKEDIN_USERNAME")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD")


@action
def search_linkedin_easy_apply(
    query: str,
    headless: bool = True,
    max_jobs: int = 25,
    remote: bool = False,
    hybrid: bool = False,
    onsite: bool = False,
    skip_ai_enrichment: bool = False,
    easy_apply_only: bool = True,
    snapshot_easy_apply: bool = True
) -> SearchResponse:
    """Phase 1: scrape LinkedIn Easy Apply jobs and store raw results in database/CSV.
    
    Args:
        query: The job search query (title, skills, company, etc.)
        headless: Whether to run the browser in headless mode (default: True)
        max_jobs: Maximum number of jobs to scrape (default: 25)
        remote: Include only Remote jobs (can be combined with others)
        hybrid: Include Hybrid jobs (can be combined)
        onsite: Include On-site jobs (can be combined)
        easy_apply_only: Restrict to Easy Apply jobs; discovery explicitly disables this.
        snapshot_easy_apply: Capture form fields; discovery always disables this.
        skip_ai_enrichment: Deprecated. AI enrichment now runs via enrich_and_generate_answers().
    
    Returns:
        Response with job_ids_found and easy_apply_job_ids arrays for Phase 2 processing.
    """
    run_id = execution_run_id("standard")
    
    # Setup logging with unique output directory
    setup_logging(
        output_dir=f"./output/{run_id}",
        enable_html_report=True,
        log_level="info"
    )
    
    try:
        log_section_start("LinkedIn Job Search", "🔍")
        
        # Log search parameters
        log.info("Search Parameters:")
        log.info(f"  Query: '{query}'")
        log.info(f"  Max jobs: {max_jobs}")
        log.info(f"  Filters: remote={remote}, hybrid={hybrid}, onsite={onsite}")
        log.info(f"  Headless: {headless}")
        
        if not skip_ai_enrichment:
            log.info("[Search] AI enrichment moved to enrich_and_generate_answers(). This action now stores raw jobs only.")
        
        configure_browser(headless_mode=headless)
        page = browser.goto("https://www.linkedin.com/jobs/search/")
        time.sleep(2)

        # Query - Enhanced search box detection with fallbacks for headless mode
        print(f"[Search] Looking for search box on page: {page.url}")
        search_box = None
        search_box_selectors = [
            # Primary: Role-based selector (most reliable in normal mode)
            ('role', "combobox", "Search by title, skill, or"),
            # Fallback 1: Direct input selector
            ('css', 'input[aria-label*="Search"]', None),
            ('css', 'input[placeholder*="Search"]', None),
            # Fallback 2: Class-based selectors
            ('css', 'input.jobs-search-box__text-input', None),
            ('css', 'input[type="text"][role="combobox"]', None),
            # Fallback 3: Generic job search input
            ('css', 'input[id*="jobs-search"]', None),
            ('css', 'input[data-test*="search"]', None),
        ]
        
        for selector_type, selector, name in search_box_selectors:
            try:
                if selector_type == 'role':
                    # Wait for the element to be visible
                    search_box = page.get_by_role(selector, name=name)
                    # Check if it exists and is visible
                    if search_box.count() > 0:
                        # Wait for it to be attached and visible
                        search_box.first.wait_for(state="visible", timeout=5000)
                        search_box = search_box.first
                        print(f"[Search] ✓ Found search box using role selector")
                        break
                else:
                    search_box = page.locator(selector).first
                    if search_box.count() > 0:
                        # Ensure it's visible before using
                        search_box.wait_for(state="visible", timeout=5000)
                        print(f"[Search] ✓ Found search box using fallback: {selector}")
                        break
            except Exception as e:
                print(f"[Search] Selector {selector_type}={selector} failed: {e}")
                search_box = None
                continue
        
        if not search_box or search_box.count() == 0:
            log_error(
                "Could not locate LinkedIn search box",
                details=f"Tried multiple selectors. Current URL: {page.url}",
                screenshot=True,
                screenshot_name="search_box_not_found_error"
            )
            raise ActionError(
                "Could not locate LinkedIn search box. "
                "This may be due to LinkedIn UI changes or authentication issues. "
                f"Current URL: {page.url}"
            )
        
        print(f"[Search] Filling search box with query: '{query}'")
        search_box.fill(query)
        search_box.press("Enter")
        print(f"[Search] Search submitted, waiting for results...")
        time.sleep(3)
        
        active_filters = _apply_search_filters(page, easy_apply_only=easy_apply_only,
            remote=remote, hybrid=hybrid, onsite=onsite)

        # Collect IDs with scrolling and pagination
        log.info("Collecting job IDs with pagination...")
        job_ids = _collect_job_ids_with_pagination(page, max_jobs)
        log.info(f"Collected {len(job_ids)} job IDs")
        
        if len(job_ids) == 0:
            log_warning(
                "No job IDs collected",
                details=f"Query: '{query}', Filters applied but no results found",
                screenshot=True,
                screenshot_name="no_jobs_found"
            )

        jobs: List[LinkedInJob] = []
        successful_job_ids = []
        easy_apply_job_ids = []
        db_written_count = 0
        
        # Process each job individually and write to DB immediately
        for i, jid in enumerate(job_ids[:max_jobs], 1):
            print(f"Processing job {i}/{min(len(job_ids), max_jobs)}: {jid}")
            
            job = _extract_from_job_page(page, jid, run_id, fast_mode=False, snapshot_easy_apply=snapshot_easy_apply, username_secret=LINKEDIN_USERNAME, password_secret=LINKEDIN_PASSWORD)
            if job:
                jobs.append(job)
                successful_job_ids.append(job.job_id)
                
                if job.easy_apply:
                    easy_apply_job_ids.append(job.job_id)
                
                # Phase 1: persist raw scrape data only. AI enrichment happens in enrich_and_generate_answers().
                job_dict = job.to_db_record()
                job_dict["processed"] = False  # ensure downstream enrichment picks it up
               
                # Write enriched data to database
                try:
                    if write_jobs is not None:
                        written = write_jobs([job_dict])  # Write single job
                        db_written_count += written
                        print(f"✓ Job {job.job_id} written to database")
                        
                except Exception as db_err:
                    print(f"✗ Failed to write job {job.job_id} to DB: {db_err}")
            else:
                print(f"✗ Skipped job {jid} due to extraction failure")

        page.close()

        # Collect successfully extracted job IDs
        # (Already calculated above during individual processing)
        
        # Log final metrics
        log_metric("Total Jobs Found", len(successful_job_ids), "jobs", "🔍")
        log_metric("Easy Apply Jobs", len(easy_apply_job_ids), "jobs", "✅")
        log_metric("Database Records Written", db_written_count, "records", "💾")
        
        # Show summary table of first 20 jobs
        if jobs:
            job_summary = [
                {
                    "Title": job.title or "N/A",
                    "Company": job.company or "N/A",
                    "Location": job.location_raw or "N/A",
                    "Easy Apply": "✅" if job.easy_apply else "❌"
                }
                for job in jobs[:20]
            ]
            embed_html_table(
                f"Jobs Found (showing {len(job_summary)} of {len(jobs)})",
                job_summary,
                level="INFO"
            )
        
        if easy_apply_job_ids:
            log.info(f"\n[Phase 1] Queued {len(easy_apply_job_ids)} Easy Apply jobs for enrichment.")
            log.info(f"[Phase 1] Run enrich_and_generate_answers(run_id='{run_id}') to process AI enrichment and answer generation.")
        
        # Write CSV file with all collected jobs
        csv_path = ""
        if jobs:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_filename = f"linkedin_jobs_{query.replace(' ', '_')}_{timestamp}.csv"
            csv_path = os.path.join(os.getcwd(), csv_filename)
            try:
                # Convert jobs to list of dicts using to_db_record
                job_dicts = [job.to_db_record() for job in jobs]
                df = pd.DataFrame(job_dicts)
                df.to_csv(csv_path, index=False)
                log.info(f"Jobs data exported to: {csv_path}")
            except Exception as e:
                log.warn(f"Warning: Failed to write CSV file: {e}")
        
        # Success - capture final state
        log_success(
            f"Job search completed successfully",
            details=f"Found {len(easy_apply_job_ids)} Easy Apply jobs out of {len(successful_job_ids)} total",
            screenshot=False  # No need for screenshot on normal success
        )
        
        log_section_end("LinkedIn Job Search", "✅")
        
        # Return simplified response with just the job IDs
        return SearchResponse(
            result=(
                f"Found {len(successful_job_ids)} jobs, {len(easy_apply_job_ids)} with Easy Apply. "
                f"Run enrich_and_generate_answers(run_id='{run_id}') for AI enrichment and answer generation."
            ),
            run_id=run_id,
            search_query=query,
            job_ids_found=successful_job_ids,
            easy_apply_job_ids=easy_apply_job_ids,
            total_jobs=len(successful_job_ids),
            attempted_count=len(job_ids[:max_jobs]),
            easy_apply_count=len(easy_apply_job_ids),
            db_records_written=db_written_count,
            csv_exported=csv_path,
            pending_enrichment_job_ids=easy_apply_job_ids,
            pending_enrichment_count=len(easy_apply_job_ids),
            filters=active_filters["active"],
            log_file=f"./output/{run_id}/log.html"
        )
    
    except ActionError as e:
        # ActionError with screenshot
        log_error(
            "Job search failed with ActionError",
            details=str(e),
            screenshot=True,
            screenshot_name="action_error"
        )
        log.exception()
        raise
    
    except Exception as e:
        # Unexpected error with screenshot
        log_error(
            "Job search failed with unexpected error",
            details=str(e),
            screenshot=True,
            screenshot_name="unexpected_error"
        )
        log.exception()
        try:
            page.close()
        except Exception:
            pass
        raise ActionError(f"Failed to search jobs: {e}")
    
    finally:
        # Always cleanup logging
        cleanup_logging()


