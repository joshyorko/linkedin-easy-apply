from sema4ai.actions import ActionError, Response, action
from robocorp import browser
import dotenv
import os
import time
import uuid
import pandas as pd
from typing import List
from datetime import datetime
from pathlib import Path

from ..utils.models import LinkedInJob
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
    skip_ai_enrichment: bool = False
) -> Response:
    """Phase 1: scrape LinkedIn Easy Apply jobs and store raw results in database/CSV.
    
    Args:
        query: The job search query (title, skills, company, etc.)
        headless: Whether to run the browser in headless mode (default: True)
        max_jobs: Maximum number of jobs to scrape (default: 25)
        remote: Include only Remote jobs (can be combined with others)
        hybrid: Include Hybrid jobs (can be combined)
        onsite: Include On-site jobs (can be combined)
        skip_ai_enrichment: Deprecated. AI enrichment now runs via enrich_and_generate_answers().
    
    Returns:
        Response with job_ids_found and easy_apply_job_ids arrays for Phase 2 processing.
    """
    run_id = f"search_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
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
        
        # Filter Easy Apply (+ optional work arrangement filters)
        # Try to click "Show all filters" button with fallback strategies
        filters_opened = False
        
        for button_name in ["Show all filters. Clicking", "Show all filters", "All filters"]:
            try:
                print(f"[Filters] Trying to find filter button: '{button_name}'")
                page.get_by_role("button", name=button_name).click(timeout=5000)
                filters_opened = True
                print(f"[Filters] ✓ Opened filters dialog")
                break
            except Exception as e:
                print(f"[Filters] Button '{button_name}' not found: {e}")
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
                    print(f"[Filters] ✓ Opened filters via CSS selector: {selector}")
                    break
                except Exception:
                    continue
        
        if not filters_opened:
            log_warning(
                "Could not open filters dialog",
                details="Proceeding without Easy Apply filter - results may include non-Easy Apply jobs",
                screenshot=True,
                screenshot_name="filters_dialog_not_opened"
            )
        time.sleep(0.8)
        
        # Easy Apply toggle (robust fallbacks) - MUST toggle this filter for Easy Apply only results
        toggled = False
        easy_apply_toggle_selectors = [
            # Switch/toggle input with label
            'input[id*="easyApply"]',
            'input[name*="easyApply"]',
            'input[aria-label*="Easy Apply"]',
            # Label that contains the toggle
            'label:has-text("Easy Apply")',
            # Switch elements
            '[role="switch"][aria-label*="Easy Apply"]',
            'button[role="switch"]:has-text("Easy Apply")',
            # LinkedIn's specific toggle structure
            'div.search-reusables__filter-binary-toggle:has-text("Easy Apply") input',
            'div.search-reusables__filter-binary-toggle:has-text("Easy Apply") label',
        ]
        
        for selector in easy_apply_toggle_selectors:
            try:
                elem = page.locator(selector).first
                if elem.count() > 0:
                    # Check if it's already checked/on
                    is_checked = elem.get_attribute('aria-checked') == 'true' or elem.is_checked() if hasattr(elem, 'is_checked') else False
                    if not is_checked:
                        elem.click(timeout=3000)
                        print(f"[Filters] ✓ Toggled Easy Apply filter via: {selector}")
                        toggled = True
                        break
                    else:
                        print(f"[Filters] Easy Apply filter already enabled")
                        toggled = True
                        break
            except Exception as e:
                print(f"[Filters] Easy Apply selector '{selector}' failed: {e}")
                continue
        
        # Fallback: try text-based clicking
        if not toggled:
            toggle_text_variants = [
                "Off Toggle Easy Apply filter",
                "Toggle Easy Apply filter", 
                "Easy Apply",
            ]
            for txt in toggle_text_variants:
                try:
                    elem = page.get_by_text(txt, exact=False).first
                    if elem.count() > 0:
                        elem.click(timeout=3000)
                        print(f"[Filters] ✓ Toggled Easy Apply via text: '{txt}'")
                        toggled = True
                        break
                except Exception:
                    pass
        
        if not toggled:
            log_warning(
                "Could not toggle Easy Apply filter",
                details="Results may include non-Easy Apply jobs. Consider running headless=False to debug.",
                screenshot=True,
                screenshot_name="easy_apply_toggle_failed"
            )

        # Apply work arrangement filters if requested
        work_filters_requested = []
        if remote: work_filters_requested.append("remote")
        if hybrid: work_filters_requested.append("hybrid")
        if onsite: work_filters_requested.append("onsite")

        if work_filters_requested:
            # Updated logic: operate inside the "All filters" dialog container to avoid picking wrong duplicates.
            # Gather container (label accessible name seems stable) else fall back to role dialog.
            try:
                filters_container = page.get_by_label("All filters", exact=True)
            except Exception:
                try:
                    filters_container = page.get_by_role("dialog")
                except Exception:
                    filters_container = page  # fallback – last resort

            # Map of arrangement -> list of pattern fragments we expect inside label text
            arrangement_label_map = {
                "remote": ["Remote Filter", "Remote (work from home)", "Remote"],
                "hybrid": ["Hybrid Filter", "Hybrid"],
                "onsite": ["On-site", "Onsite"],
            }

            def try_click_patterns(container, patterns: List[str]) -> str | None:
                for pat in patterns:
                    # First try specific label elements combining text fragments like "Remote Filter by Remote"
                    try:
                        label_locator = container.locator("label").filter(has_text=pat)
                        if label_locator.count() > 0:
                            label_locator.first.click(timeout=2000)
                            return pat
                    except Exception:
                        pass
                    # Fallback: any text node inside container
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
                    print(f"Applied work arrangement filter: {mode} via pattern '{applied_pattern}'")
                else:
                    # As a final attempt, enumerate label texts and pick the first containing the keyword
                    try:
                        keyword = mode.replace("onsite", "On").split()[0].replace("remote", "Remote").replace("hybrid", "Hybrid")
                        labels = filters_container.locator("label")
                        count = labels.count()
                        for i in range(min(count, 40)):  # safety cap
                            txt = labels.nth(i).inner_text(timeout=1000)
                            if keyword.lower() in txt.lower():
                                try:
                                    labels.nth(i).click()
                                    print(f"Applied work arrangement filter by scan: {mode} -> '{txt[:60]}'")
                                    break
                                except Exception:
                                    pass
                        else:
                            print(f"Warning: Could not apply work arrangement filter: {mode}")
                    except Exception:
                        print(f"Warning: Could not apply work arrangement filter (scan failed): {mode}")

        # Apply filters
        try:
            # Support multiple possible button label variants
            apply_variants = [
                "Apply current filters to show",
                "Apply filters",
                "Show results",
                "View results"
            ]
            applied_btn = False
            for name in apply_variants:
                try:
                    btn = page.get_by_role("button", name=name).first
                    if btn.count() > 0:
                        btn.click(timeout=5000)
                        applied_btn = True
                        print(f"[Filters] ✓ Clicked apply filters button: '{name}'")
                        break
                except Exception:
                    pass
            if not applied_btn:
                # Try a generic footer button inside filters container
                try:
                    page.get_by_label("All filters", exact=True).get_by_role("button").filter(has_text="Apply").first.click()
                    applied_btn = True
                    print(f"[Filters] ✓ Applied filters via dialog button")
                except Exception:
                    print("Warning: Could not find an Apply/Show results button; proceeding anyway")
        except Exception:
            # Fallback: alternative phrasing LinkedIn sometimes uses
            pass
        time.sleep(2.5)

        search_url = page.url
        
        # Verify Easy Apply filter is active by checking URL
        if 'f_AL=true' in search_url:
            print(f"[Filters] ✓ Easy Apply filter confirmed active in URL")
        else:
            log_warning(
                "Easy Apply filter may not be active",
                details=f"URL does not contain f_AL=true. Current URL: {search_url}",
                screenshot=True,
                screenshot_name="easy_apply_filter_not_in_url"
            )

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
            
            job = _extract_from_job_page(page, jid, run_id, fast_mode=False, snapshot_easy_apply=True, username_secret=LINKEDIN_USERNAME, password_secret=LINKEDIN_PASSWORD)
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
        return Response(result={
            "run_id": run_id,
            "search_query": query,
            "job_ids_found": successful_job_ids,
            "easy_apply_job_ids": easy_apply_job_ids,
            "total_jobs": len(successful_job_ids),
            "easy_apply_count": len(easy_apply_job_ids),
            "db_records_written": db_written_count,
            "csv_exported": csv_path,
            "pending_enrichment_job_ids": easy_apply_job_ids,
            "pending_enrichment_count": len(easy_apply_job_ids),
            "filters": {
                "remote": remote,
                "hybrid": hybrid,
                "onsite": onsite
            },
            "message": (
                f"Found {len(successful_job_ids)} jobs, {len(easy_apply_job_ids)} with Easy Apply. "
                f"Run enrich_and_generate_answers(run_id='{run_id}') for AI enrichment and answer generation."
            ),
            "log_file": f"./output/{run_id}/log.html"
        })
    
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


