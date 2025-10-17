from sema4ai.actions import ActionError, Response, action
import dotenv
import os
import time
import random
import pandas as pd
from typing import List, Dict, Any, Optional
from datetime import datetime
from threading import Thread, Lock
from queue import Queue

# Import Playwright - robocorp-browser depends on it
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    # Fallback if direct import fails
    import sys
    from robocorp import browser as rb_browser
    # Playwright should be in the same environment as robocorp-browser
    from playwright.sync_api import sync_playwright

from ..utils.models import LinkedInJob
from ..utils.db import write_jobs
from ..utils.tools import _collect_job_ids_with_pagination, _extract_from_job_page
from ..utils.robolog import setup_logging, log, cleanup_logging
from ..utils.robolog_screenshots import (
    log_section_start, log_section_end,
    log_success, log_warning, log_error,
    log_metric, embed_html_table
)

dotenv.load_dotenv()

# Global LinkedIn credentials
LINKEDIN_USERNAME = os.getenv("LINKEDIN_USERNAME")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD")

# Thread-safe lock for database writes
db_write_lock = Lock()


def _worker_scrape_jobs(
    worker_id: int,
    job_ids: List[str],
    run_id: str,
    headless: bool,
    results_queue: Queue,
    context_dir: str
):
    """Worker function that runs in its own thread with its own browser instance.
    
    Args:
        worker_id: Unique identifier for this worker
        job_ids: List of job IDs to process
        run_id: Search run identifier
        headless: Whether to run in headless mode
        results_queue: Queue to put results into
        context_dir: Browser context directory for session persistence
    """
    jobs = []
    failed_jobs = {}  # Track failed jobs: {job_id: error_message}
    print(f"[Worker {worker_id}] Starting with {len(job_ids)} jobs")
    
    worker_context_dir = None
    try:
        # Each worker gets its own Playwright instance
        with sync_playwright() as p:
            # Create a worker-specific temporary context directory to avoid conflicts
            import tempfile
            import shutil
            
            # Create temp directory for this worker
            temp_base = tempfile.gettempdir()
            worker_context_dir = os.path.join(temp_base, f"linkedin_worker_{worker_id}_{os.getpid()}")
            
            # Copy cookies from main context if it exists
            if os.path.exists(context_dir):
                # Copy the entire context directory for this worker
                try:
                    shutil.copytree(context_dir, worker_context_dir)
                    print(f"[Worker {worker_id}] Copied browser context to temp: {worker_context_dir}")
                except Exception as e:
                    print(f"[Worker {worker_id}] Could not copy context: {e}")
            
            # Launch browser with persistent context for login
            browser_context = p.chromium.launch_persistent_context(
                user_data_dir=worker_context_dir,
                headless=headless,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                ]
            )
            
            # Get the first page or create one
            if len(browser_context.pages) > 0:
                page = browser_context.pages[0]
            else:
                page = browser_context.new_page()
            
            print(f"[Worker {worker_id}] Browser launched")
            
            # Process each job
            for i, job_id in enumerate(job_ids, 1):
                print(f"[Worker {worker_id}] Processing job {i}/{len(job_ids)}: {job_id}")
                
                # Add random delay between jobs to avoid rate limiting (2-5 seconds)
                if i > 1:  # Don't delay before first job
                    delay = random.uniform(2.0, 5.0)
                    time.sleep(delay)
                
                # Retry logic for failed extractions
                max_retries = 2
                retry_count = 0
                job = None
                
                while retry_count <= max_retries and job is None:
                    try:
                        if retry_count > 0:
                            print(f"[Worker {worker_id}] Retry {retry_count}/{max_retries} for job {job_id}")
                            # Exponential backoff on retries
                            backoff_delay = 2 ** retry_count * random.uniform(1, 2)
                            time.sleep(backoff_delay)
                        
                        job_url = f"https://www.linkedin.com/jobs/view/{job_id}/"
                        page.goto(job_url, timeout=20000, wait_until="domcontentloaded")
                        time.sleep(random.uniform(2.0, 4.0))  # Random delay for more natural behavior
                        
                        # Use the comprehensive extraction function from tools.py
                        # Convert Playwright page to work with _extract_from_job_page
                        job = _extract_from_job_page(
                            page, 
                            job_id, 
                            run_id, 
                            fast_mode=False, 
                            snapshot_easy_apply=True,
                            username_secret=LINKEDIN_USERNAME,
                            password_secret=LINKEDIN_PASSWORD
                        )
                        
                        if job:
                            jobs.append(job)
                            print(f"[Worker {worker_id}] ✓ Extracted job {job_id}")
                            break  # Success, exit retry loop
                        else:
                            print(f"[Worker {worker_id}] ✗ Failed to extract job {job_id}, attempt {retry_count + 1}")
                            retry_count += 1
                            
                    except Exception as e:
                        print(f"[Worker {worker_id}] Error processing job {job_id} (attempt {retry_count + 1}): {e}")
                        retry_count += 1
                        if retry_count > max_retries:
                            error_msg = f"Max retries exceeded: {str(e)}"
                            failed_jobs[job_id] = error_msg
                            print(f"[Worker {worker_id}] ✗ Failed job {job_id} after {max_retries} retries: {error_msg}")
            
            # Close browser
            browser_context.close()
            print(f"[Worker {worker_id}] Completed {len(jobs)}/{len(job_ids)} jobs successfully")
            if failed_jobs:
                print(f"[Worker {worker_id}] Failed jobs: {list(failed_jobs.keys())}")
            
            # Cleanup temporary context directory
            if worker_context_dir and os.path.exists(worker_context_dir):
                try:
                    import shutil
                    shutil.rmtree(worker_context_dir)
                    print(f"[Worker {worker_id}] Cleaned up temp context: {worker_context_dir}")
                except Exception as e:
                    print(f"[Worker {worker_id}] Could not cleanup temp context: {e}")
            
    except Exception as e:
        print(f"[Worker {worker_id}] Fatal error: {e}")
        # Cleanup on error too
        if worker_context_dir and os.path.exists(worker_context_dir):
            try:
                import shutil
                shutil.rmtree(worker_context_dir)
            except Exception:
                pass
    
    # Put results in queue (include both successful jobs and failed job tracking)
    results_queue.put((worker_id, jobs, failed_jobs))


@action
def parallel_search_linkedin_easy_apply(
    query: str,
    headless: bool = False,
    max_jobs: int = 10,
    parallel_workers: int = 3,  # Changed from 5 to 3 - LinkedIn rate limits above 3-4 concurrent
    remote: bool = False,
    hybrid: bool = False,
    onsite: bool = False
) -> Response:
    """Parallel job search using multiple browser instances (RAW PLAYWRIGHT).
    
    This action spawns multiple browser windows that scrape jobs simultaneously.
    Each worker runs in its own thread with its own Playwright browser instance.
    
    Args:
        query: The job search query (title, skills, company, etc.)
        headless: Whether to run browsers in headless mode (default: False)
        max_jobs: Maximum number of jobs to scrape (default: 10)
        parallel_workers: Number of parallel browser instances (default: 5)
        remote: Include only Remote jobs (can be combined with others)
        hybrid: Include Hybrid jobs (can be combined)
        onsite: Include On-site jobs (can be combined)
    
    Returns:
        Response with job_ids_found and processing statistics.
    """
    run_id = f"parallel_search_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Setup logging
    setup_logging(
        output_dir=f"./output/{run_id}",
        enable_html_report=True,
        log_level="info"
    )
    
    try:
        log_section_start("Parallel LinkedIn Job Search", "🚀")
        
        log.info("Search Parameters:")
        log.info(f"  Query: '{query}'")
        log.info(f"  Max jobs: {max_jobs}")
        log.info(f"  Parallel workers: {parallel_workers}")
        log.info(f"  Headless: {headless}")
        log.info(f"  Filters: remote={remote}, hybrid={hybrid}, onsite={onsite}")
        
        # Warn about rate limiting with >3 workers
        if parallel_workers > 3:
            log_warning(
                f"Using {parallel_workers} parallel workers - High risk of LinkedIn rate limiting!",
                details="LinkedIn typically allows 3-4 concurrent connections. Consider using parallel_workers=3 for best results."
            )
        
        # Shared browser context directory
        context_dir = os.path.join(os.getcwd(), "browser_context")
        
        if not os.path.exists(context_dir):
            log_warning(
                "No browser context found",
                details=f"Browser context directory not found at {context_dir}. Run set_browser_context first to log in."
            )
            raise ActionError("No browser context found. Please run set_browser_context(headless_mode=False) first to log into LinkedIn.")
        
        # Use Playwright directly for initial search and ID collection
        log.info("Collecting job IDs using main browser instance...")
        job_ids = []
        
        with sync_playwright() as p:
            # Use the main browser context for initial search
            browser_context = p.chromium.launch_persistent_context(
                user_data_dir=context_dir,
                headless=headless,
                args=['--no-sandbox', '--disable-dev-shm-usage']
            )
            
            if len(browser_context.pages) > 0:
                page = browser_context.pages[0]
            else:
                page = browser_context.new_page()
            
            page.goto("https://www.linkedin.com/jobs/search/", timeout=30000)
            time.sleep(2)
            
            # Query - Enhanced search box detection with fallbacks (EXACT COPY FROM search.py)
            log.info(f"Looking for search box on page: {page.url}")
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
                        search_box = page.get_by_role(selector, name=name)
                        if search_box.count() > 0:
                            search_box.first.wait_for(state="visible", timeout=5000)
                            search_box = search_box.first
                            log.info(f"✓ Found search box using role selector")
                            break
                    else:
                        search_box = page.locator(selector).first
                        if search_box.count() > 0:
                            search_box.wait_for(state="visible", timeout=5000)
                            log.info(f"✓ Found search box using fallback: {selector}")
                            break
                except Exception as e:
                    log.info(f"Selector {selector_type}={selector} failed: {e}")
                    search_box = None
                    continue
            
            if not search_box or search_box.count() == 0:
                log_error(
                    "Could not locate LinkedIn search box",
                    details=f"Tried multiple selectors. Current URL: {page.url}",
                    screenshot=True
                )
                browser_context.close()
                raise ActionError(f"Could not locate LinkedIn search box. Current URL: {page.url}")
            
            log.info(f"Filling search box with query: '{query}'")
            search_box.fill(query)
            search_box.press("Enter")
            log.info(f"Search submitted, waiting for results...")
            time.sleep(3)
            
            # Filter Easy Apply (+ optional work arrangement filters) - EXACT COPY FROM search.py
            # Try to click "Show all filters" button with fallback strategies
            filters_opened = False
            
            for button_name in ["Show all filters. Clicking", "Show all filters", "All filters"]:
                try:
                    log.info(f"Trying to find filter button: '{button_name}'")
                    page.get_by_role("button", name=button_name).click(timeout=5000)
                    filters_opened = True
                    log.info(f"✓ Opened filters dialog")
                    break
                except Exception as e:
                    log.info(f"Button '{button_name}' not found: {e}")
                    continue
            
            if not filters_opened:
                # Try direct CSS selectors as fallback
                filter_css_selectors = [
                    'button[aria-label*="Show all filters"]',
                    'button:has-text("All filters")',
                    'button[aria-label*="filters"]',
                ]
                for selector in filter_css_selectors:
                    try:
                        page.locator(selector).first.click(timeout=3000)
                        filters_opened = True
                        log.info(f"✓ Opened filters via CSS selector: {selector}")
                        break
                    except Exception:
                        continue
            
            if not filters_opened:
                log_warning(
                    "Could not open filters dialog",
                    details="Proceeding without Easy Apply filter - results may include non-Easy Apply jobs"
                )
            time.sleep(0.8)
            
            # Easy Apply toggle (robust fallbacks) - EXACT COPY FROM search.py
            toggled = False
            toggle_text_variants = [
                "Off Toggle Easy Apply filter",
                "Toggle Easy Apply filter",
                "Easy Apply",
            ]

            for txt in toggle_text_variants:
                try:
                    page.get_by_text(txt, exact=False).click()
                    toggled = True
                    log.info(f"✓ Toggled Easy Apply filter")
                    break
                except Exception:
                    pass
            if not toggled:
                log.info("Warning: Could not positively toggle Easy Apply filter (may already be on)")

            # Apply work arrangement filters if requested - EXACT COPY FROM search.py
            work_filters_requested = []
            if remote: work_filters_requested.append("remote")
            if hybrid: work_filters_requested.append("hybrid")
            if onsite: work_filters_requested.append("onsite")

            if work_filters_requested:
                try:
                    filters_container = page.get_by_label("All filters", exact=True)
                except Exception:
                    try:
                        filters_container = page.get_by_role("dialog")
                    except Exception:
                        filters_container = page

                arrangement_label_map = {
                    "remote": ["Remote Filter", "Remote (work from home)", "Remote"],
                    "hybrid": ["Hybrid Filter", "Hybrid"],
                    "onsite": ["On-site", "Onsite"],
                }

                def try_click_patterns(container, patterns: list) -> str | None:
                    for pat in patterns:
                        try:
                            label_locator = container.locator("label").filter(has_text=pat)
                            if label_locator.count() > 0:
                                label_locator.first.click(timeout=2000)
                                return pat
                        except Exception:
                            pass
                        try:
                            container.get_by_text(pat, exact=False).first.click(timeout=2000)
                            return pat
                        except Exception:
                            pass
                    return None

                for mode in work_filters_requested:
                    patterns = arrangement_label_map.get(mode, [])
                    applied_pattern = try_click_patterns(filters_container, patterns)
                    if applied_pattern:
                        log.info(f"✓ Applied work arrangement filter: {mode} via pattern '{applied_pattern}'")
                    else:
                        try:
                            keyword = mode.replace("onsite", "On").split()[0].replace("remote", "Remote").replace("hybrid", "Hybrid")
                            labels = filters_container.locator("label")
                            count = labels.count()
                            for i in range(min(count, 40)):
                                txt = labels.nth(i).inner_text(timeout=1000)
                                if keyword.lower() in txt.lower():
                                    try:
                                        labels.nth(i).click()
                                        log.info(f"✓ Applied work arrangement filter by scan: {mode} -> '{txt[:60]}'")
                                        break
                                    except Exception:
                                        pass
                            else:
                                log.info(f"Warning: Could not apply work arrangement filter: {mode}")
                        except Exception:
                            log.info(f"Warning: Could not apply work arrangement filter (scan failed): {mode}")

            # Apply filters - EXACT COPY FROM search.py
            try:
                apply_variants = [
                    "Apply current filters to show",
                    "Apply filters",
                    "Show results",
                    "View results"
                ]
                applied_btn = False
                for name in apply_variants:
                    try:
                        page.get_by_role("button", name=name).click()
                        applied_btn = True
                        log.info(f"✓ Applied filters")
                        break
                    except Exception:
                        pass
                if not applied_btn:
                    try:
                        page.get_by_label("All filters", exact=True).get_by_role("button").filter(has_text="Apply").first.click()
                        applied_btn = True
                        log.info(f"✓ Applied filters (fallback)")
                    except Exception:
                        log.info("Warning: Could not find an Apply/Show results button; proceeding anyway")
            except Exception:
                pass
            time.sleep(2.5)

            # Collect job IDs with pagination - using same approach as search.py
            log.info("Collecting job IDs with pagination...")
            job_ids = _collect_job_ids_with_pagination(page, max_jobs)
            log.info(f"Collected {len(job_ids)} job IDs")
            
            browser_context.close()
        
        if len(job_ids) == 0:
            log_warning(
                "No job IDs collected",
                details=f"Query: '{query}', Filters applied but no results found",
                screenshot=True,
                screenshot_name="no_jobs_found"
            )
            return Response(result={
                "run_id": run_id,
                "search_query": query,
                "total_jobs": 0,
                "message": "No jobs found",
                "log_file": f"./output/{run_id}/log.html"
            })
        
        # Split job IDs into batches for parallel processing
        jobs_to_process = job_ids[:max_jobs]
        batch_size = max(1, len(jobs_to_process) // parallel_workers)
        job_batches = [
            jobs_to_process[i:i + batch_size]
            for i in range(0, len(jobs_to_process), batch_size)
        ]
        
        log.info(f"Processing {len(jobs_to_process)} jobs across {len(job_batches)} workers...")
        log.info(f"Batch sizes: {[len(batch) for batch in job_batches]}")
        
        # Create results queue
        results_queue = Queue()
        
        # Launch worker threads with staggered starts to avoid rate limiting
        threads = []
        for worker_id, batch in enumerate(job_batches, 1):
            # Stagger worker starts by 5-10 seconds to avoid simultaneous connections and rate limiting
            if worker_id > 1:
                stagger_delay = random.uniform(5.0, 10.0)
                log.info(f"Waiting {stagger_delay:.1f}s before starting worker {worker_id}...")
                time.sleep(stagger_delay)
            
            t = Thread(
                target=_worker_scrape_jobs,
                args=(worker_id, batch, run_id, headless, results_queue, context_dir)
            )
            t.start()
            threads.append(t)
            log.info(f"Started worker {worker_id} with {len(batch)} jobs")
        
        # Wait for all threads to complete
        for t in threads:
            t.join()
        
        # Collect results from queue
        all_jobs = []
        successful_job_ids = []
        easy_apply_job_ids = []
        all_failed_jobs = {}  # Collect failed jobs from all workers
        db_written_count = 0
        
        while not results_queue.empty():
            worker_id, jobs, failed_jobs = results_queue.get()
            log.info(f"[Worker {worker_id}] Returned {len(jobs)} successful jobs, {len(failed_jobs)} failed")
            all_jobs.extend(jobs)
            all_failed_jobs.update(failed_jobs)
        
        # Log failed jobs summary
        if all_failed_jobs:
            log.warn(f"⚠️ {len(all_failed_jobs)} jobs failed extraction:")
            for job_id, error in all_failed_jobs.items():
                log.warn(f"  • Job {job_id}: {error}")
        
        # Write to database
        for job in all_jobs:
            successful_job_ids.append(job.job_id)
            if job.easy_apply:
                easy_apply_job_ids.append(job.job_id)
            
            job_dict = job.to_db_record()
            job_dict["processed"] = False
            
            try:
                with db_write_lock:
                    written = write_jobs([job_dict])
                    db_written_count += written
            except Exception as e:
                print(f"Failed to write job {job.job_id}: {e}")
        
        # Log metrics
        log_metric("Total Jobs Found", len(successful_job_ids), "jobs", "🔍")
        log_metric("Easy Apply Jobs", len(easy_apply_job_ids), "jobs", "✅")
        log_metric("Database Records Written", db_written_count, "records", "💾")
        
        # Show summary table
        if all_jobs:
            job_summary = [
                {
                    "Title": job.title or "N/A",
                    "Company": job.company or "N/A",
                    "Location": job.location_raw or "N/A",
                    "Easy Apply": "✅" if job.easy_apply else "❌"
                }
                for job in all_jobs[:20]
            ]
            embed_html_table(
                f"Jobs Found (showing {len(job_summary)} of {len(all_jobs)})",
                job_summary,
                level="INFO"
            )
        
        log_success(
            "Parallel job search completed",
            details=f"Found {len(easy_apply_job_ids)} Easy Apply jobs out of {len(successful_job_ids)} total"
        )
        
        # Write CSV file with all collected jobs (same as search.py)
        csv_path = ""
        if all_jobs:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_filename = f"linkedin_jobs_{query.replace(' ', '_')}_{timestamp}.csv"
            csv_path = os.path.join(os.getcwd(), csv_filename)
            try:
                job_dicts = [job.to_db_record() for job in all_jobs]
                df = pd.DataFrame(job_dicts)
                df.to_csv(csv_path, index=False)
                log.info(f"Jobs data exported to: {csv_path}")
            except Exception as e:
                log.warn(f"Warning: Failed to write CSV file: {e}")
        
        if easy_apply_job_ids:
            log.info(f"\n[Phase 1] Queued {len(easy_apply_job_ids)} Easy Apply jobs for enrichment.")
            log.info(f"[Phase 1] Run enrich_and_generate_answers(run_id='{run_id}') to process AI enrichment and answer generation.")
        
        log_section_end("Parallel LinkedIn Job Search", "✅")
        
        return Response(result={
            "run_id": run_id,
            "search_query": query,
            "job_ids_found": successful_job_ids,
            "easy_apply_job_ids": easy_apply_job_ids,
            "failed_job_ids": list(all_failed_jobs.keys()),
            "failed_jobs_details": all_failed_jobs,
            "total_jobs": len(successful_job_ids),
            "easy_apply_count": len(easy_apply_job_ids),
            "failed_count": len(all_failed_jobs),
            "db_records_written": db_written_count,
            "csv_exported": csv_path,
            "pending_enrichment_job_ids": easy_apply_job_ids,
            "pending_enrichment_count": len(easy_apply_job_ids),
            "filters": {
                "remote": remote,
                "hybrid": hybrid,
                "onsite": onsite
            },
            "parallel_workers_used": len(job_batches),
            "message": (
                f"Found {len(successful_job_ids)} jobs, {len(easy_apply_job_ids)} with Easy Apply using {len(job_batches)} parallel workers. "
                f"{len(all_failed_jobs)} jobs failed extraction. "
                f"Run enrich_and_generate_answers(run_id='{run_id}') for AI enrichment and answer generation."
            ),
            "log_file": f"./output/{run_id}/log.html"
        })
    
    except ActionError as e:
        # ActionError with screenshot (same as search.py)
        log_error(
            "Parallel search failed with ActionError",
            details=str(e),
            screenshot=True,
            screenshot_name="action_error"
        )
        log.exception()
        raise
    
    except Exception as e:
        # Unexpected error with screenshot (same as search.py)
        log_error(
            "Parallel search failed with unexpected error",
            details=str(e),
            screenshot=True,
            screenshot_name="unexpected_error"
        )
        log.exception()
        raise ActionError(f"Parallel search failed: {e}")
    
    finally:
        cleanup_logging()
