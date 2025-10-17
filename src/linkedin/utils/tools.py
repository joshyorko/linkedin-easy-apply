from robocorp import browser
from typing import Optional, Dict, Any
def _load_profile() -> Optional[Dict[str, Any]]:
    """Load user profile from database (primary) with JSON fallback."""
    try:
        # Load from database (source of truth)
        from .db import get_active_profile
        profile = get_active_profile()
        if profile:
            print(f"[Profile] Loaded active profile from database")
            return profile
        print(f"[Profile] No profile found in database")
        return None
    except Exception as e:
        print(f"[Profile] Failed to load: {e}")
        return None

import os
from robocorp import browser
import dotenv
import os
import time
import uuid
import re
import json
from typing import List, Optional, Dict, Any, Set
from datetime import datetime
from urllib.parse import urljoin

from .models import LinkedInJob

from .enhanced_extraction import enhance_job_extraction


dotenv.load_dotenv()

# Global LinkedIn credentials from environment variables
LINKEDIN_USERNAME = os.getenv("LINKEDIN_USERNAME")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD")




# Performance toggles (env-controlled to preserve action signature)
FAST_SCRAPE: bool = (os.getenv("FAST_SCRAPE", "1").lower() not in ("0", "false", "no"))
SNAPSHOT_EASY_APPLY: bool = (os.getenv("SNAPSHOT_EASY_APPLY", "0").lower() in ("1", "true", "yes"))


def _detect_step_info(dlg) -> Dict[str, Any]:
    """Detect current step and total steps from the Easy Apply modal.

    Strategies (in priority order):
    1. Progress region with aria-label percentage (most reliable for LinkedIn)
    2. Progressbar element with aria-valuenow/aria-valuemax
    3. Parse visible text like "Step X of Y" or "X of Y"
    4. Inspect stepper elements with aria-current="step" and count siblings
    
    Returns a dict: {"current": Optional[int], "total": Optional[int], "progress": Optional[int]}
    """
    info: Dict[str, Optional[int]] = {"current": None, "total": None, "progress": None, "percent": None}
    print(f"[Step Detection] Starting detection on dialog...")
    try:
        # PRIORITY 1: Use aria-label on region (most reliable for LinkedIn)
        try:
            region = dlg.locator('[role="region"]').first
            region_count = region.count()
            print(f"[Step Detection] Found {region_count} region elements")
            
            if region_count > 0:
                aria_label = region.get_attribute('aria-label') or ''
                print(f"[Step Detection] Region aria-label: '{aria_label}'")
                match = re.search(r'(\d+)\s*percent', aria_label, re.IGNORECASE)
                if match:
                    progress = int(match.group(1))
                    info["progress"] = progress
                    info["percent"] = progress
                    
                    # Calculate step from progress (LinkedIn uses 25% increments for 5 steps)
                    if progress == 0:
                        info["current"] = 1
                        info["total"] = 5
                    elif progress > 0 and progress < 100:
                        # Detect increment pattern: 25% = 5 steps, 33% = 4 steps, 50% = 3 steps
                        if progress % 25 == 0:
                            info["total"] = 5
                            info["current"] = (progress // 25) + 1
                        elif progress % 33 == 0 or progress in [33, 66]:
                            info["total"] = 4
                            info["current"] = (progress // 33) + 1
                        elif progress == 50:
                            info["total"] = 3
                            info["current"] = 2
                        else:
                            # Unknown pattern, use percentage as approximate step
                            info["current"] = int(progress / 20) + 1  # Rough estimate
                            info["total"] = 5  # Assume 5 as default
                    elif progress == 100:
                        info["current"] = info.get("total", 5)
                        if info["total"] is None:
                            info["total"] = 5
                    
                    print(f"[Step Detection] Progress: {progress}%, Step {info['current']}/{info['total']}")
                    return info
        except Exception as e:
            print(f"[Step Detection] Region aria-label method failed: {e}")
        
        # PRIORITY 2: ARIA progressbar
        try:
            bars = dlg.locator('[role="progressbar"]').all()
        except Exception:
            bars = []
        for bar in bars:
            try:
                now = bar.get_attribute('aria-valuenow') or bar.get_attribute('value')
                maxv = bar.get_attribute('aria-valuemax') or bar.get_attribute('max')
                if now and maxv and now.isdigit() and maxv.isdigit():
                    info["current"] = int(now)
                    info["total"] = int(maxv)
                    progress_calc = int((int(now) / int(maxv)) * 100)
                    info["progress"] = progress_calc
                    info["percent"] = progress_calc
                    return info
            except Exception:
                continue

        # PRIORITY 3: Text patterns like "Step X of Y" or "X of Y"
        try:
            txt = (dlg.inner_text() or '').strip()
        except Exception:
            txt = ''
        if txt:
            m = re.search(r'(?:step\s*)?(\d+)\s*of\s*(\d+)', txt, re.IGNORECASE)
            if m:
                try:
                    info["current"] = int(m.group(1))
                    info["total"] = int(m.group(2))
                    # approximate progress if we have both
                    try:
                        info["progress"] = int((info["current"] / info["total"]) * 100)
                        info["percent"] = info["progress"]
                    except Exception:
                        pass
                    return info
                except Exception:
                    pass

        # PRIORITY 4: Stepper with aria-current="step"
        try:
            current = dlg.locator('[aria-current="step"]').first
            if current and current.count() > 0:
                try:
                    # Count siblings/peers that represent steps
                    peers = current.locator('xpath=ancestor::*[self::ol or self::ul][1]/li')
                    total = peers.count()
                    # Determine index of current among peers (1-based)
                    curr_idx = None
                    for i in range(min(total, 20)):
                        try:
                            li = peers.nth(i)
                            if li.locator('[aria-current="step"]').count() > 0:
                                curr_idx = i + 1
                                break
                        except Exception:
                            continue
                    if curr_idx:
                        info["current"] = curr_idx
                        info["total"] = total if total > 0 else None
                        # approximate progress
                        try:
                            if info["total"]:
                                info["progress"] = int((info["current"] / info["total"]) * 100)
                                info["percent"] = info["progress"]
                        except Exception:
                            pass
                        return info
                except Exception:
                    pass
        except Exception:
            pass
    except Exception:
        pass
    return info



US_STATE_ABBREV = {
    'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA','KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA','WV','WI','WY','DC'
}

US_STATE_NAMES = {
    'alabama','alaska','arizona','arkansas','california','colorado','connecticut','delaware','florida','georgia','hawaii','idaho','illinois','indiana','iowa','kansas','kentucky','louisiana','maine','maryland','massachusetts','michigan','minnesota','mississippi','missouri','montana','nebraska','nevada','new hampshire','new jersey','new mexico','new york','north carolina','north dakota','ohio','oklahoma','oregon','pennsylvania','rhode island','south carolina','south dakota','tennessee','texas','utah','vermont','virginia','washington','west virginia','wisconsin','wyoming','district of columbia'
}

def parse_location(location_text: str) -> Dict[str, Any]:
    """Parse location string into structured data with support for state-only inputs."""
    text = (location_text or '').strip()
    location: Dict[str, Any] = {
        "raw_location": text,
        "city": None,
        "state": None,
        "country": None,
        "location_type": None,
    }

    if not text:
        return location

    # Extract and remove location type tokens
    for lt in ("Remote", "Hybrid", "On-site"):
        if re.search(rf"\b{lt}\b", text, re.IGNORECASE):
            location["location_type"] = lt
            # remove trailing paren like "(Hybrid)" or inline token
            text = re.sub(r"\(.*?\)", "", text)
            text = re.sub(rf"\b{lt}\b", "", text, flags=re.IGNORECASE)
    text = text.replace("·", " ").strip()

    # Clean parentheses leftovers and extra spaces
    text = re.sub(r"\s+", " ", text).strip()

    # Split parts by comma
    parts = [p.strip() for p in text.split(",") if p.strip()]

    # Cases:
    # 1) City, ST [, Country]
    # 2) City, State Name [, Country]
    # 3) State Name, Country (no city)
    # 4) Country only
    if len(parts) >= 3:
        # Assume City, State, Country
        city, state_part, country = parts[0], parts[1], parts[2]
        if len(state_part) == 2 and state_part.upper() in US_STATE_ABBREV:
            location["city"] = city
            location["state"] = state_part.upper()
            location["country"] = country
        elif state_part.lower() in US_STATE_NAMES:
            location["city"] = city
            location["state"] = state_part.title()
            location["country"] = country
        else:
            # Fallback: treat first as city, last as country
            location["city"] = city
            location["country"] = parts[-1]
            if len(parts) > 2:
                middle = ", ".join(parts[1:-1])
                location["state"] = middle
    elif len(parts) == 2:
        a, b = parts
        # If second token looks like country
        if b.lower() in {"united states", "usa", "u.s.a.", "us"}:
            # a could be city or state name
            if len(a) == 2 and a.upper() in US_STATE_ABBREV:
                location["state"] = a.upper()
            elif a.lower() in US_STATE_NAMES:
                location["state"] = a.title()
            else:
                location["city"] = a
            location["country"] = "United States"
        else:
            # Likely City, ST or City, State Name
            if len(b) == 2 and b.upper() in US_STATE_ABBREV:
                location["city"] = a
                location["state"] = b.upper()
                location["country"] = "United States"
            elif b.lower() in US_STATE_NAMES:
                location["city"] = a
                location["state"] = b.title()
                location["country"] = "United States"
            else:
                # Generic City, Country
                location["city"] = a
                location["country"] = b
    else:
        # Single token: could be country or state
        token = parts[0] if parts else text
        if len(token) == 2 and token.upper() in US_STATE_ABBREV:
            location["state"] = token.upper()
            location["country"] = "United States"
        elif token.lower() in US_STATE_NAMES:
            location["state"] = token.title()
            location["country"] = "United States"
        else:
            # Treat as city or country unknown
            location["city"] = token

    return location


def parse_compensation(comp_text: str) -> Dict[str, Any]:
    """Parse compensation string into structured data"""
    compensation = {
        "raw_compensation": comp_text,
        "salary_range": None,
        "benefits": []
    }
    comp = comp_text or ""
    # Extract salary range with support for k/K/m/M and common units
    salary_match = re.search(r'\$[\d,.]+([kKmM])?(?:\s*(?:/|per)\s*(?:yr|year|mo|month|hr|hour))?\s*[-–]\s*\$[\d,.]+([kKmM])?(?:\s*(?:/|per)\s*(?:yr|year|mo|month|hr|hour))?', comp)
    if salary_match:
        compensation["salary_range"] = salary_match.group(0)
    
    # Extract benefits
    if "·" in comp:
        parts = comp.split("·")
        for part in parts[1:]:  # Skip salary part
            benefit = part.strip()
            if benefit and benefit != compensation["salary_range"]:
                compensation["benefits"].append(benefit)
    
    return compensation


def normalize_applicant_count(text: Optional[str]) -> Optional[str]:
    """Return just the numeric applicant count as a string (e.g., '96'), or None."""
    if not text:
        return None
    m = re.search(r'(\d[\d,]*)\s+applicants?', text, re.IGNORECASE)
    if m:
        return m.group(1).replace(',', '')
    return None


def normalize_relative_date(text: Optional[str], ref: Optional[datetime] = None) -> Optional[str]:
    """Convert relative times like '10 minutes ago', '2 hours ago', '3 days ago', '1 month ago' to ISO timestamp.

    If no relative time is found, return the original text (caller may trim/handle).
    """
    if not text:
        return None
    ref_dt = ref or datetime.now()
    t = text.strip().lower()
    # Support minutes, hours, days, weeks, months
    m = re.search(r'(\d+)\s*(minute|min|hour|day|week|month)s?\s+ago', t)
    if not m:
        return text  # fallback to raw if unrecognized
    n = int(m.group(1))
    unit = m.group(2)
    from datetime import timedelta
    if unit in ('minute', 'min'):
        dt = ref_dt - timedelta(minutes=n)
    elif unit == 'hour':
        dt = ref_dt - timedelta(hours=n)
    elif unit == 'day':
        dt = ref_dt - timedelta(days=n)
    elif unit == 'week':
        dt = ref_dt - timedelta(weeks=n)
    else:  # month
        dt = ref_dt - timedelta(days=30 * n)
    return dt.isoformat()


def extract_job_id_from_url(job_url: str) -> str:
    """Extract LinkedIn job ID from URL"""
    match = re.search(r'/jobs/view/(\d+)', job_url)
    return match.group(1) if match else ""


# =============================================================================
# Job Data Extraction Utilities
# =============================================================================
# These functions extract specific fields from job pages/cards with multiple
# fallback strategies. They work in both contexts:
# - 'card': Job list cards (search results)
# - 'detail': Full job detail pages (direct URL navigation)
# =============================================================================

def extract_job_title(page_or_element, context='detail', existing_title=None):
    """Extract job title with multiple fallback strategies.
    
    Args:
        page_or_element: Playwright page or locator
        context: 'card' for job list cards, 'detail' for full job pages
        existing_title: Optional title to avoid when extracting other fields
    
    Returns:
        str: Job title or "Unknown Title"
    """
    selectors = {
        'card': [
            'strong',
            'h3',
            'h4',
            '[data-testid*="title"]',
            '.job-card-list__title',
            'a[data-control-name*="job_card_title"]'
        ],
        'detail': [
            'h1.job-details-jobs-unified-top-card__job-title',
            'h1.t-24',
            'h1',
            '.job-details-jobs-unified-top-card__job-title',
            '[data-testid*="job-title"]',
            'strong'
        ]
    }
    
    for selector in selectors.get(context, selectors['detail']):
        try:
            elem = page_or_element.locator(selector).first
            if elem.count() > 0:
                title = elem.inner_text().strip()
                if title:
                    return title
        except Exception:
            continue
    
    return "Unknown Title"


def extract_company_name(page_or_element, context='detail', existing_title=None):
    """Extract company name with multiple fallback strategies.
    
    Args:
        page_or_element: Playwright page or locator
        context: 'card' for job list cards, 'detail' for full job pages
        existing_title: Optional title to avoid extracting as company
    
    Returns:
        str: Company name or "Unknown Company"
    """
    selectors = {
        'card': [
            'h4 + *',  # Element after h4 (title)
            '.job-card-container__primary-description',
            'a[data-control-name*="company_name"]',
            '[data-testid*="company"]',
            '.job-card-list__company-name'
        ],
        'detail': [
            '.job-details-jobs-unified-top-card__company-name',
            'a.ember-view',
            '[data-testid*="company"]',
            '.t-black'
        ]
    }
    
    for selector in selectors.get(context, selectors['detail']):
        try:
            elem = page_or_element.locator(selector).first
            if elem.count() > 0:
                company_text = elem.inner_text().strip()
                if company_text and company_text != existing_title:
                    return company_text
        except Exception:
            continue
    
    # Fallback: search within all text elements (card context only)
    if context == 'card' and not existing_title:
        try:
            all_elements = page_or_element.locator('*').all()
            for elem in all_elements:
                try:
                    text = elem.inner_text().strip()
                    # Skip if it's the title or too short/long
                    if text and text != existing_title and 3 < len(text) < 100:
                        # Check if it looks like a company name
                        if not any(punct in text for punct in ['·', '•', '$', '/', 'applicant']):
                            return text
                except Exception:
                    continue
        except Exception:
            pass
    
    return "Unknown Company"


def extract_location_data(page_or_element, context='detail'):
    """Extract location with multiple fallback strategies.
    
    Args:
        page_or_element: Playwright page or locator
        context: 'card' for job list cards, 'detail' for full job pages
    
    Returns:
        dict: Parsed location data (raw_location, city, state, country, location_type)
    """
    location_text = ""
    
    if context == 'card':
        # Look for location patterns in generic elements
        try:
            location_elements = page_or_element.locator('generic').all()
            for elem in location_elements:
                text = elem.inner_text()
                if any(pattern in text for pattern in ["Remote", "On-site", "Hybrid", ",", " ("]):
                    location_text = text
                    break
        except Exception:
            pass
    else:  # detail
        # Try detail page selectors
        selectors = [
            '.job-details-jobs-unified-top-card__bullet',
            '[data-testid*="location"]',
            '.t-black--light'
        ]
        for selector in selectors:
            try:
                elem = page_or_element.locator(selector).first
                if elem.count() > 0:
                    location_text = elem.inner_text().strip()
                    if location_text:
                        break
            except Exception:
                continue
    
    return parse_location(location_text)


def extract_job_url_and_id(page_or_element, existing_title=None):
    """Extract job URL and ID with multiple fallback strategies.
    
    Args:
        page_or_element: Playwright page or locator (typically a job card element)
        existing_title: Optional title to help find the right link
    
    Returns:
        tuple: (job_url, job_id) or ("", "")
    """
    job_link = ""
    job_link_selectors = [
        f'a:has-text("{existing_title}")' if existing_title else None,  # Link containing title
        'a[href*="/jobs/view/"]',  # Direct job link
        'a[data-control-name*="job_card"]',  # Job card link
        'a'  # Any link as fallback
    ]
    
    for selector in job_link_selectors:
        if selector is None:
            continue
        try:
            job_link_element = page_or_element.locator(selector).first
            if job_link_element.count() > 0:
                href = job_link_element.get_attribute('href')
                if href and '/jobs/view/' in href:
                    job_link = href
                    break
        except Exception:
            continue
    
    if job_link and not job_link.startswith('http'):
        from urllib.parse import urljoin
        job_link = urljoin("https://www.linkedin.com", job_link)
    
    job_id = extract_job_id_from_url(job_link)
    return job_link, job_id


def detect_easy_apply_availability(page_or_element, context='card'):
    """Detect if Easy Apply is available with multiple fallback strategies.
    
    Args:
        page_or_element: Playwright page or locator
        context: 'card' for job list cards, 'detail' for full job pages
    
    Returns:
        bool: True if Easy Apply is available
    """
    easy_apply_selectors = [
        'generic:has-text("Easy Apply")',
        'button:has-text("Easy Apply")',
        '*:has-text("Easy Apply")',
        '[data-testid*="easy-apply"]',
        '[aria-label*="Easy Apply"]'
    ]
    
    for selector in easy_apply_selectors:
        try:
            if page_or_element.locator(selector).count() > 0:
                return True
        except Exception:
            continue
    
    return False


def extract_compensation_data(page_or_element, context='detail'):
    """Extract compensation with multiple fallback strategies.
    
    Args:
        page_or_element: Playwright page or locator
        context: 'card' for job list cards, 'detail' for full job pages
    
    Returns:
        dict: Parsed compensation data (raw_compensation, salary_range, benefits)
    """
    compensation_text = ""
    
    # Try to find salary elements
    try:
        salary_elements = page_or_element.locator('*:has-text("$")').all()
        for elem in salary_elements:
            text = elem.inner_text()
            if "$" in text and any(x in text for x in ["K/yr", "/yr", "/year", "/mo", "/hour"]):
                compensation_text = text
                break
    except Exception:
        pass
    
    # Fallback approach if needed
    if not compensation_text:
        try:
            all_elements = page_or_element.locator('*').all()
            for elem in all_elements:
                try:
                    text = elem.inner_text()
                    if "$" in text and any(x in text for x in ["K/yr", "/yr", "/year", "/mo", "/hour"]):
                        compensation_text = text
                        break
                except Exception:
                    continue
        except Exception:
            pass
    
    return parse_compensation(compensation_text) if compensation_text else {
        "raw_compensation": "",
        "salary_range": None,
        "benefits": []
    }


def extract_application_status(page_or_element, context='card'):
    """Extract application status metadata.
    
    Args:
        page_or_element: Playwright page or locator
        context: 'card' for job list cards, 'detail' for full job pages
    
    Returns:
        dict: Status data (is_viewed, applicant_count, status_message, promoted_by_hirer)
    """
    status = {
        "is_viewed": False,
        "applicant_count": None,
        "status_message": None,
        "promoted_by_hirer": False
    }
    
    try:
        # Check if viewed
        status["is_viewed"] = page_or_element.locator('generic:has-text("Viewed")').count() > 0
        
        # Check applicant count
        applicant_elements = page_or_element.locator('generic').all()
        for elem in applicant_elements:
            text = elem.inner_text()
            if "applicant" in text.lower():
                status["applicant_count"] = text
                break
        
        # Check for status messages
        if page_or_element.locator('generic:has-text("Actively reviewing applicants")').count() > 0:
            status["status_message"] = "Actively reviewing applicants"
        
        # Check if promoted
        status["promoted_by_hirer"] = page_or_element.locator('generic:has-text("Promoted")').count() > 0
        
    except Exception:
        pass
    
    return status


def extract_job_metadata(page, context='detail'):
    """Extract job metadata (date posted, job type, verified company).
    
    Args:
        page: Playwright page
        context: 'card' for job list cards, 'detail' for full job pages
    
    Returns:
        dict: Metadata (date_posted, job_type, verified_company)
    """
    metadata = {
        "date_posted": None,
        "job_type": None,
        "verified_company": False
    }
    
    try:
        # Extract date posted
        date_elements = page.locator('*:has-text("ago")').all()
        for elem in date_elements:
            text = elem.inner_text()
            if any(word in text for word in ["week", "day", "month", "hour", "minute"]):
                metadata["date_posted"] = text
                break
        
        # Extract job type
        if page.locator('text="Full-time"').count() > 0:
            metadata["job_type"] = "Full-time"
        elif page.locator('text="Part-time"').count() > 0:
            metadata["job_type"] = "Part-time"
        elif page.locator('text="Contract"').count() > 0:
            metadata["job_type"] = "Contract"
        
        # Check for verified company (works on both page and element)
        metadata["verified_company"] = page.locator('svg[aria-label*="verification"]').count() > 0
        
    except Exception:
        pass
    
    return metadata


def extract_job_description(page, context='detail'):
    """Extract full job description text.
    
    Args:
        page: Playwright page
        context: 'card' for job list cards, 'detail' for full job pages
    
    Returns:
        str: Job description or empty string
    """
    if context != 'detail':
        return ""
    
    selectors = [
        '.jobs-description__content',
        '.jobs-description-content',
        '[data-testid*="job-description"]',
        '.job-details-jobs-unified-top-card__job-description'
    ]
    
    for selector in selectors:
        try:
            desc_el = page.locator(selector).first
            if desc_el.count() > 0:
                return desc_el.inner_text().strip()
        except Exception:
            continue
    
    return ""


def _find_results_container(page):
    """Best-effort locator for the left-side results list container."""
    # Try to return the actual scrollable list container; LinkedIn changes often.
    selectors = [
        # Common UL list containers
        'ul.scaffold-layout__list-container',
        'ul.jobs-search__results-list',
        'ul.jobs-search-results__list',
        # Scrollable wrappers that contain the UL
        'div.jobs-search-results-list',
        'section.two-pane-serp-page__results-list',
        'div.jobs-search__results-list',
        # Generic fallbacks
        'main .jobs-search-results',
        'main'
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc and loc.count() > 0:
                return loc
        except Exception:
            continue
    return page.locator('main').first


def _collect_job_ids_with_scroll(page, max_jobs: int) -> List[str]:
    """Scroll the results list on the current page to collect up to max_jobs unique job IDs.

    Loosened early-exit conditions to better handle lazy-loading/infinite-scroll result lists
    where content appears in bursts. This prevents prematurely stopping after a handful of items.
    """
    collected: List[str] = []
    seen: Set[str] = set()
    list_container = _find_results_container(page)
    prev_seen_count = -1
    stable_rounds = 0
    no_new_jobs_rounds = 0  # Track rounds with no new jobs

    def _click_show_more_if_present() -> bool:
        # Some result views have a "See more jobs" or "Show more" button that loads more results
        btn_selectors = [
            'button:has-text("See more jobs")',
            'button:has-text("Show more")',
            'button[aria-label*="See more"]',
        ]
        for sel in btn_selectors:
            try:
                btn = page.locator(sel).first
                if btn and btn.count() > 0 and btn.is_visible():
                    try:
                        btn.click(timeout=2000)
                        time.sleep(0.4)
                        return True
                    except Exception:
                        continue
            except Exception:
                continue
        return False

    # Progressive scroll within container and page as fallback
    # Increased rounds and relaxed stability thresholds to avoid premature exit
    for round_num in range(30):
        jobs_before_round = len(collected)
        
        # Prefer anchors inside the results area to avoid picking up stray links
        try:
            cards = list_container.locator('a[href*="/jobs/view/"]')
        except Exception:
            cards = page.locator('a[href*="/jobs/view/"]')
        try:
            count = cards.count()
        except Exception:
            count = 0
        # Iterate through currently visible anchors; new ones will appear on subsequent rounds
        for i in range(min(count, 200)):
            try:
                href = cards.nth(i).get_attribute('href') or ''
                m = re.search(r'/jobs/view/(\d+)', href)
                if not m:
                    continue
                jid = m.group(1)
                if jid not in seen:
                    seen.add(jid)
                    collected.append(jid)
                    if len(collected) >= max_jobs:
                        return collected
            except Exception:
                continue

        # Early exit if no new jobs found in several consecutive rounds
        jobs_after_round = len(collected)
        if jobs_after_round == jobs_before_round:
            no_new_jobs_rounds += 1
            # Give more headroom for slow loading lists
            if no_new_jobs_rounds >= 5:
                break
        else:
            no_new_jobs_rounds = 0  # Reset counter when we find new jobs

        # Scroll the results container and page to load more
        scrolled = False
        try:
            # Scroll by chunks to trigger incremental load
            list_container.evaluate("el => el.scrollTop = el.scrollTop + Math.max(600, Math.floor(el.clientHeight * 0.9))")
            scrolled = True
        except Exception:
            pass
        if not scrolled:
            try:
                list_container.evaluate("el => el.scrollTop = el.scrollHeight")
                scrolled = True
            except Exception:
                pass
        # Hover the list then wheel the mouse to ensure the right pane scrolls
        try:
            list_container.hover()
            page.mouse.wheel(0, 2000)
            scrolled = True
        except Exception:
            pass

        # Occasionally try clicking show more if available (every 3rd round)
        if round_num % 3 == 0:
            _click_show_more_if_present()

        # Short wait to allow new items to render
        time.sleep(0.25)

        # Stop when no more new anchors appear after a few rounds
        current_seen = len(seen)
        if current_seen == prev_seen_count:
            stable_rounds += 1
            # Require 2 stable rounds before deciding we've reached the end of this page
            if stable_rounds >= 2:
                break
        else:
            stable_rounds = 0
        prev_seen_count = current_seen

    return collected


def _go_to_next_results_page(page) -> bool:
    """Attempt to move to next results page.

    Strategy:
    1) First check if we're already on the last page (no next button or disabled)
    2) Click known 'Next' pagination controls (various selectors).
    3) Fallback: increment the 'start' query param by 25 and navigate.
    """
    try:
        # OPTIMIZED: Early detection of last page by checking pagination state
        # Check for disabled "Next" buttons or pagination indicators
        disabled_next_selectors = [
            'nav[aria-label="Pagination"] button[aria-label="Next"][aria-disabled="true"]',
            'nav[aria-label="Pagination"] button[aria-label="Next"][disabled]',
            'nav[aria-label="Pagination"] li.artdeco-pagination__indicator--next[aria-disabled="true"]',
            'button[aria-label="Next"][aria-disabled="true"]',
            'button[aria-label="Next"][disabled]',
        ]
        
        for sel in disabled_next_selectors:
            try:
                if page.locator(sel).count() > 0:
                    # Found disabled next button - we're on last page
                    return False
            except Exception:
                continue
        
        # Check for presence of a next button; absence no longer means "stop" because some
        # result views rely on querystring pagination (start=25,50,...) without rendering a Next control.
        next_button_exists = False
        next_selectors = [
            'nav[aria-label="Pagination"] button[aria-label="Next"]',
            'nav[aria-label="Pagination"] li.artdeco-pagination__indicator--next button',
            'button[aria-label="Next"]',
            'button[aria-label*="Next"]',
        ]
        
        for sel in next_selectors:
            try:
                if page.locator(sel).count() > 0:
                    next_button_exists = True
                    break
            except Exception:
                continue
        
        # If no visible next button was found, we'll attempt URL start-param fallback below

        # Prefer visible and enabled next buttons
        candidates = [
            # Common LinkedIn pagination controls
            'nav[aria-label="Pagination"] button[aria-label="Next"]',
            'nav[aria-label="Pagination"] li.artdeco-pagination__indicator--next button',
            'nav[aria-label="Pagination"] a[aria-label="Next"]',
            'button[aria-label="Next"]',
            'button[aria-label*="Next"]',
            'a[aria-label="Next"]',
            # Sometimes uses 'Page next'
            'button[aria-label="Page next"]',
            'a[aria-label="Page next"]',
            # Newer data-test hook
            'li[data-test-pagination-page-btn="next"] button',
            # Fallbacks by text
            'button:has-text("Next")',
            'a:has-text("Next")',
        ]
        for sel in candidates:
            try:
                btn = page.locator(sel).first
                if not btn or btn.count() == 0:
                    continue
                # Skip disabled
                aria_disabled = btn.get_attribute('aria-disabled')
                disabled = btn.get_attribute('disabled')
                if (aria_disabled and aria_disabled.lower() == 'true') or disabled is not None:
                    # OPTIMIZED: Don't try to scroll for disabled buttons, just return False
                    return False
                    
                previous_url = page.url
                # Store current job count to detect if navigation actually worked
                try:
                    current_job_count = page.locator('a[href*="/jobs/view/"]').count()
                except Exception:
                    current_job_count = 0
                
                # OPTIMIZED: reduced timeout from 6000 to 2000ms
                btn.click(timeout=2000)
                
                # Wait for either URL change or content update
                # OPTIMIZED: reduced from 10 to 5 iterations with faster checks
                navigation_success = False
                for _ in range(5):
                    time.sleep(0.1)  # OPTIMIZED: reduced from 0.2 to 0.1 seconds
                    try:
                        if page.url != previous_url:
                            navigation_success = True
                            break
                        # Also check if job listings changed (alternative success indicator)
                        new_job_count = page.locator('a[href*="/jobs/view/"]').count()
                        if new_job_count != current_job_count and new_job_count > 0:
                            navigation_success = True
                            break
                    except Exception:
                        pass
                
                if navigation_success:
                    return True
                
            except Exception:
                continue
    except Exception:
        pass

    # OPTIMIZED: Simplified fallback with better last page detection
    try:
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
        current = page.url
        parsed = urlparse(current)
        qs = parse_qs(parsed.query)
        try:
            start = int(qs.get('start', [0])[0] or 0)
        except Exception:
            start = 0
        next_start = start + 25
        qs['start'] = [str(next_start)]
        new_query = urlencode(qs, doseq=True)
        new_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
        if new_url != current:
            previous_url = current
            # Store current job count before navigation
            try:
                current_job_count = page.locator('a[href*="/jobs/view/"]').count()
            except Exception:
                current_job_count = 0
            
            # Navigate to the next page using query parameter pagination
            page.goto(new_url, timeout=12000)
            
            # Wait briefly and check if we got new content
            for _ in range(10):
                time.sleep(0.1)
                try:
                    if page.url != previous_url:
                        # Check if we actually got new jobs (not just redirected to same page)
                        new_job_count = page.locator('a[href*="/jobs/view/"]').count()
                        if new_job_count > 0 and new_job_count != current_job_count:
                            return True
                        elif new_job_count == 0:
                            # Empty page = last page reached
                            return False
                        else:
                            return True  # URL changed, assume success
                except Exception:
                    pass
        return False
    except Exception:
        return False


def _collect_job_ids_with_pagination(page, max_jobs: int) -> List[str]:
    """Collect job IDs by scrolling and then paginating until we reach max_jobs or run out of pages.

    Fully dynamic pagination:
    - Continues until max_jobs is reached OR LinkedIn runs out of results
    - No arbitrary page limits - will paginate as far as needed
    - Stops automatically when 2-3 consecutive pages return no new jobs
    - Safety cap at 1000 pages to prevent infinite loops (supports 7000+ jobs at ~7 jobs/page)
    """
    all_ids: List[str] = []
    seen: set[str] = set()
    
    # Fully dynamic: calculate pages needed based on actual request
    # LinkedIn typically shows 7-10 jobs per page
    jobs_per_page_estimate = 7
    # Calculate expected pages needed, with generous buffer
    expected_pages = (max_jobs + jobs_per_page_estimate - 1) // jobs_per_page_estimate
    # Safety cap to prevent infinite loops (1000 pages = ~7000 jobs)
    max_pages = min(1000, max(expected_pages + 10, 50))
    
    consecutive_empty_pages = 0  # Track empty pages to detect end faster
    
    for page_index in range(max_pages):
        remaining = max_jobs - len(all_ids)
        if remaining <= 0:
            break
            
        # Give a short wait for results list to settle on each page
        for _ in range(10):
            try:
                if page.locator('a[href*="/jobs/view/"]').count() > 0:
                    break
            except Exception:
                pass
            time.sleep(0.1)  # OPTIMIZED: reduced from 0.2 to 0.1 seconds

        # Track jobs before collecting from this page
        jobs_before = len(all_ids)
        print(f"[Pagination] Page {page_index+1}: collecting up to {remaining} jobs...")
        page_ids = _collect_job_ids_with_scroll(page, remaining)
        
        # Add new unique job IDs
        new_jobs_this_page = 0
        for jid in page_ids:
            if jid not in seen:
                seen.add(jid)
                all_ids.append(jid)
                new_jobs_this_page += 1
                
        print(f"[Pagination] Page {page_index+1}: found {new_jobs_this_page} new ids (total: {len(all_ids)})")
        # Early exit if no new jobs found on this page
        if new_jobs_this_page == 0:
            consecutive_empty_pages += 1
            if consecutive_empty_pages >= 2:  # Exit after 2 consecutive empty pages
                break
        else:
            consecutive_empty_pages = 0  # Reset counter when we find jobs
            
        if len(all_ids) >= max_jobs:
            break
            
        # Attempt to go to next page (via button or start-param fallback). If navigation fails,
        # allow one more retry in case the UI needed a moment to render pagination controls.
        print(f"[Pagination] Attempting to navigate to next results page...")
        navigated = _go_to_next_results_page(page)
        if not navigated:
            time.sleep(0.5)
            navigated = _go_to_next_results_page(page)
            if not navigated:
                print(f"[Pagination] No further pages available. Stopping at {len(all_ids)} ids.")
                break

        # Give the next page a short moment to populate
        print(f"[Pagination] Moved to next page.")
        time.sleep(0.8)
        
    return all_ids


def _extract_from_job_page(page, job_id: str, run_id: str, fast_mode: bool = FAST_SCRAPE, snapshot_easy_apply: bool = SNAPSHOT_EASY_APPLY, username_secret=None, password_secret=None) -> Optional[LinkedInJob]:
    """Navigate to a job page and extract structured details and optional Easy Apply snapshot."""
    try:
        job_url = f"https://www.linkedin.com/jobs/view/{job_id}/"
        # OPTIMIZED: reduced timeout from 30000 to 15000ms
        page.goto(job_url, timeout=15000)
        # Wait for details header or company/title area
        # Try multiple anchors as LinkedIn changes DOM often
        # OPTIMIZED: reduced max_checks for fast_mode from 8 to 5, non-fast from 20 to 10
        max_checks = 5 if fast_mode else 10
        sleep_between = 0.1 if fast_mode else 0.15  # OPTIMIZED: reduced sleep times
        for _ in range(max_checks):
            try:
                if page.locator('[data-test-job-header-title], h1').count() > 0:
                    break
            except Exception:
                pass
            time.sleep(sleep_between)
        if not fast_mode:
            time.sleep(0.3)  # OPTIMIZED: reduced from 0.5 to 0.3 seconds


        # --- Robust selectors for job detail page ---
        # Title
        title = ""
        el = page.locator('main h1').first
        if el.count() > 0:
            try:
                title = (el.inner_text() or '').strip()
            except Exception:
                pass

        # Company - Enhanced extraction with multiple strategies
        company = ""
        try:
            # Strategy 1: Look for company link in job header (expanded selectors)
            company_selectors = [
                'main h4 a[href*="/company/"]',
                'main .jobs-unified-top-card__company-name a',
                'main [data-test*="company"] a',
                'main a[href*="/company/"]',
                'main .job-details-jobs-unified-top-card__company-name',
                'main .display-flex.align-items-center.flex-1',
                'main a.XrBcczxbbctlDvNxyOeSrWsgNCUYGXfTvRc'
            ]
            for selector in company_selectors:
                el = page.locator(selector).first
                if el.count() > 0:
                    try:
                        company_text = (el.inner_text() or '').strip()
                        if company_text and company_text != title and not any(word in company_text.lower() for word in ['ago', 'applicant', 'promoted']):
                            company = company_text
                            break
                    except Exception:
                        continue
            # Strategy 2: Look for company text (not linked)
            if not company:
                company_fallback_selectors = [
                    'main h4',
                    'main .jobs-unified-top-card__company-name',
                    'main [data-test*="company"]',
                    'main .job-details-jobs-unified-top-card__company-name',
                    'main .display-flex.align-items-center.flex-1',
                    'main a.XrBcczxbbctlDvNxyOeSrWsgNCUYGXfTvRc'
                ]
                for selector in company_fallback_selectors:
                    elements = page.locator(selector).all()
                    for el in elements:
                        try:
                            text = (el.inner_text() or '').strip()
                            if (text and text != title and not '·' in text and len(text) > 1 and len(text) < 100 and not any(word in text.lower() for word in ['ago', 'applicant', 'promoted'])):
                                company = text
                                break
                        except Exception:
                            continue
                    if company:
                        break
        except Exception as e:
            print(f"Error in enhanced company extraction: {e}")
            # Fallback to original approach
            el = page.locator('main h4 a').first
            if el.count() > 0:
                try:
                    company = (el.inner_text() or '').strip()
                except Exception:
                    pass

        # Location - Enhanced extraction with pattern matching
        location_text = ""
        try:
            # Strategy 1: Find dedicated location elements (expanded selectors)
            location_selectors = [
                'main .jobs-unified-top-card__bullet',
                'main .jobs-details-top-card__bullet',
                'main [data-test*="location"]',
                'main .job-details-jobs-unified-top-card__container--two-pane span',
                'main .job-details-jobs-unified-top-card__primary-description-container',
                'main span.tvm__text.tvm__text--low-emphasis'
            ]
            location_pattern = r'([^·]+(?:Remote|Hybrid|On-site|,\s*[A-Z]{2}|,\s*United States))'
            for selector in location_selectors:
                elements = page.locator(selector).all()
                for el in elements:
                    try:
                        text = (el.inner_text() or '').strip()
                        # Accept if it looks like a city/state or location
                        if re.search(location_pattern, text, re.IGNORECASE) or re.match(r'^[A-Za-z .-]+,\s*[A-Z]{2}$', text) or re.match(r'^[A-Za-z .-]+$', text):
                            if not any(word in text.lower() for word in ['applicant', 'ago', 'promoted', 'about', 'show']):
                                location_text = text.replace('·', '').strip()
                                break
                    except Exception:
                        continue
                if location_text:
                    break
            # Strategy 2: Text analysis for location patterns in main content
            if not location_text:
                try:
                    main_content = page.locator('main').inner_text()
                    lines = [line.strip() for line in main_content.split('\n') if line.strip()]
                    for line in lines:
                        if (len(line) < 100 and not any(word in line.lower() for word in ['applicant', 'ago', 'promoted', 'about', 'show']) and
                            (re.search(r'(Remote|Hybrid|On-site)', line, re.IGNORECASE) or
                             re.search(r'[A-Za-z\s]+,\s*[A-Z]{2}', line) or
                             re.search(r'[A-Za-z\s]+,\s*United States', line))):
                            location_text = line.replace('·', '').strip()
                            break
                except Exception as e:
                    print(f"Error in location text analysis: {e}")
            # Strategy 3: Look near company element for location info
            if not location_text and company:
                try:
                    company_elements = page.locator(f'main *:has-text("{company}")').all()
                    for comp_el in company_elements:
                        try:
                            parent = comp_el.locator('xpath=..')
                            parent_text = parent.inner_text()
                            for line in parent_text.split('\n'):
                                line = line.strip()
                                if (line and line != company and
                                    (re.search(location_pattern, line, re.IGNORECASE) or
                                     any(word in line for word in ['Remote', 'Hybrid', 'On-site']))):
                                    location_text = line.replace('·', '').strip()
                                    break
                            if location_text:
                                break
                        except Exception:
                            continue
                except Exception as e:
                    print(f"Error in company-based location search: {e}")
        except Exception as e:
            print(f"Error in enhanced location extraction: {e}")
            el = page.locator('main h4').first
            if el.count() > 0:
                sib = el.locator('xpath=following-sibling::*[1]').first
                if sib.count() > 0:
                    try:
                        location_text = (sib.inner_text() or '').replace('·', '').strip()
                    except Exception:
                        pass
        location = parse_location(location_text)

        # Date posted (look for span with 'ago')
        date_posted = None
        el = page.locator('main span:has-text("ago")').first
        if el.count() > 0:
            try:
                raw_date = (el.inner_text() or '').strip()
                date_posted = normalize_relative_date(raw_date)
            except Exception:
                pass

        # Applicants (look for span with 'applicant')
        applicant_count = None
        el = page.locator('main span:has-text("applicant")').first
        if el.count() > 0:
            try:
                raw_applicants = (el.inner_text() or '').strip()
                applicant_count = normalize_applicant_count(raw_applicants)
            except Exception:
                pass

        # Job description - light vs deep extraction
        job_description = ""
        try:
            if fast_mode:
                # Prefer a direct description node when available, avoid large scans
                desc_candidates = [
                    'main [data-test*="job-description"]',
                    'main .jobs-description__content',
                    'main section:has(h2:has-text("About the job"))',
                ]
                for sel in desc_candidates:
                    node = page.locator(sel).first
                    if node and node.count() > 0:
                        try:
                            txt = (node.inner_text() or '').strip()
                            if len(txt) > 50:
                                job_description = txt[:3000]  # trim to keep it light
                                break
                        except Exception:
                            continue
                if not job_description:
                    # Minimal fallback: first substantial paragraph in main
                    main_text = page.locator('main').inner_text()
                    paras = [p.strip() for p in main_text.split('\n\n') if len(p.strip()) > 150]
                    if paras:
                        job_description = paras[0][:3000]
            else:
                # Existing deep extraction path (unchanged)
                # Strategy 1: Look for "About the job" section
                about_selectors = [
                    'main h2:has-text("About the job")',
                    'main h3:has-text("About the job")',
                    'main *:has-text("About the job")',
                    'main [data-test*="job-description"]'
                ]
                for selector in about_selectors:
                    header = page.locator(selector).first
                    if header.count() > 0:
                        try:
                            containers_to_try = [
                                header.locator('xpath=..'),
                                header.locator('xpath=../following-sibling::*[1]'),
                                header.locator('xpath=../../..')
                            ]
                            for container in containers_to_try:
                                if container.count() > 0:
                                    container_text = container.inner_text().strip()
                                    container_text = re.sub(r'^.*?About the job.*?\n', '', container_text, flags=re.IGNORECASE)
                                    container_text = re.split(r'\n(?:Skills|Requirements|Qualifications|Benefits|Apply|Show)', container_text)[0]
                                    if len(container_text) > 50:
                                        job_description = container_text.strip()
                                        break
                            if job_description:
                                break
                        except Exception:
                            continue
                if not job_description:
                    try:
                        text_elements = page.locator('main p, main div, main span').all()
                        potential_descriptions = []
                        for el in text_elements:
                            try:
                                text = el.inner_text().strip()
                                if (len(text) > 100 and len(text) < 5000 and not text.lower().startswith(('about the job', 'show more', 'show less', 'report', 'save', 'apply')) and not any(ui in text.lower() for ui in ['linkedin', 'profile', 'connection', 'follow', 'message', 'notification', 'settings', 'home', 'my network']) and any(k in text.lower() for k in ['responsible','experience','skills','requirements','role','position','candidate','team','work','develop','manage','support','collaborate','ability','knowledge'])):
                                    potential_descriptions.append(text)
                            except Exception:
                                continue
                        if potential_descriptions:
                            potential_descriptions.sort(key=len, reverse=True)
                            job_description = potential_descriptions[0]
                    except Exception as e:
                        print(f"Error in intelligent content analysis: {e}")
                if not job_description:
                    try:
                        main_content = page.locator('main').inner_text()
                        paragraphs = main_content.split('\n\n')
                        for paragraph in paragraphs:
                            paragraph = paragraph.strip()
                            if (len(paragraph) > 200 and any(pattern in paragraph.lower() for pattern in ['we are looking','you will','responsibilities','role involves','candidate will','position requires','join our team'])):
                                job_description = paragraph
                                break
                        if not job_description:
                            paragraphs = [p.strip() for p in paragraphs if len(p.strip()) > 100]
                            if paragraphs:
                                filtered = [p for p in paragraphs if not any(w in p.lower() for w in ['linkedin','profile','network','settings'])]
                                job_description = max(filtered or paragraphs, key=len)
                    except Exception as e:
                        print(f"Error in fallback content extraction: {e}")
        except Exception as e:
            print(f"Error in job description extraction: {e}")

        # Compensation (look for $ in main)
        compensation = {"raw_compensation": "", "salary_range": None, "benefits": []}
        el = page.locator('main :text("$")').first
        if el.count() > 0:
            try:
                comp_text = el.inner_text().strip()
                compensation = parse_compensation(comp_text)
            except Exception:
                pass

        # Job type (look for 'Full-time', etc. in main)
        job_type = None
        for k in ["Full-time", "Part-time", "Contract", "Internship", "Temporary"]:
            if page.locator(f'main :text("{k}")').count() > 0:
                job_type = k
                break

        # Verified company (look for verification icon in main)
        verified_company = page.locator('main svg[aria-label*="verification"]').count() > 0

        # Easy Apply detection
        easy_apply = False
        questions_json = None
        answer_template = None
        form_elements: Dict[str, Any] = {}
        form_snapshot_url: str = ""
        try:
            easy_btn = page.locator('main button:has-text("Easy Apply")').first
            easy_apply = easy_btn.count() > 0
            # Capture snapshot whenever enabled; in fast mode we do a lighter traversal inside the dialog
            if easy_apply and snapshot_easy_apply:
                snap = _open_easy_apply_and_snapshot(page)
                if snap:
                    form_elements = snap.get('form_elements', {})
                    questions_data = snap.get('questions_json')
                    if questions_data:
                        questions_json = json.dumps(questions_data)
                    tmpl = snap.get('answer_template')
                    if tmpl:
                        # Store as JSON string for DB/CSV
                        answer_template = json.dumps(tmpl)
                    form_snapshot_url = snap.get('form_snapshot_url', '') or ''
        except Exception:
            pass

        # Status message (actively reviewing, promoted, etc.)
        status_message = None
        if page.locator('main :text("Actively reviewing applicants")').count() > 0:
            status_message = 'Actively reviewing applicants'
        promoted_by_hirer = page.locator('main :text("Promoted")').count() > 0

        job = LinkedInJob(
            title=title,
            company=company,
            job_id=job_id,
            job_url=job_url,
            location_raw=location["raw_location"],
            location_city=location["city"],
            location_state=location["state"],
            location_country=location["country"],
            location_type=location["location_type"],
            easy_apply=easy_apply,
            is_viewed=False,  # Set default to False for detail page
            applicant_count=applicant_count,
            status_message=status_message,
            promoted_by_hirer=promoted_by_hirer,
            salary_range=compensation["salary_range"],
            benefits=compensation["benefits"],
            compensation_raw=compensation["raw_compensation"],
            date_posted=date_posted,
            job_type=job_type,
            verified_company=verified_company,
            form_snapshot_url=form_snapshot_url,
            form_elements=form_elements,
            questions_json=questions_json,
            answer_template=answer_template,
            run_id=run_id,
            job_description=job_description
        )
        
        # Note: raw_html is commented out in the model but handled by to_db_record() via getattr
        # Enhance the job data with missing fields (skip in fast mode)
        if not fast_mode:
            job_dict = job.model_dump()
            enhanced_job_dict = enhance_job_extraction(job_dict, page, job_description)
            return LinkedInJob(**enhanced_job_dict)
        return job

    except Exception as e:
        print(f"Error extracting job page {job_id}: {e}")
        return None


def _open_easy_apply_and_snapshot(page) -> Optional[Dict[str, Any]]:
    """Open Easy Apply modal, snapshot fields into a compact questions_json, then close it.

    Traverses all available steps (Next/Review) until the end, with a safe upper bound.
    Returns form elements and questions data structure for AI answer generation.
    """
    try:
        # Enhanced Easy Apply button detection with multiple strategies
        easy_apply_clicked = False
        try:
            btn = page.get_by_role("button", name=re.compile(r"Easy Apply", re.I)).first
            if btn.count() > 0:
                btn.click(timeout=10000)
                easy_apply_clicked = True
        except Exception as e:
            print(f"Role-based Easy Apply click failed: {e}")
        if not easy_apply_clicked:
            easy_apply_selectors = [
                'button:has-text("Easy Apply")',
                '[aria-label*="Easy Apply"]',
                'button[data-test*="easy-apply"]',
                'button[class*="easy-apply"]',
                '*:has-text("Easy Apply"):is(button, [role="button"])'
            ]
            for selector in easy_apply_selectors:
                try:
                    btn = page.locator(selector).first
                    if btn.count() > 0:
                        btn.click(timeout=10000)
                        easy_apply_clicked = True
                        break
                except Exception as e:
                    print(f"Selector {selector} failed: {e}")
                    continue
        if not easy_apply_clicked:
            print("Could not find or click Easy Apply button")
            return None
        for _ in range(40):
            if page.locator('[role="dialog"]').count() > 0:
                break
            time.sleep(0.1)
        time.sleep(0.6)  # Increased wait for dialog to fully render
        dlg = page.locator('[role="dialog"]').first
        form_elements: Dict[str, Any] = {}
        questions: List[Dict[str, Any]] = []

        def collect_inputs_from_dialog(dlg_local):
            """Collect form inputs from current step - optimized to reduce scrolling"""
            nonlocal form_elements, questions
            inputs_local = dlg_local.locator('input, select, textarea')
            n_local = inputs_local.count()
            # Reduced from 200 to 50 to minimize excessive scrolling
            for i in range(min(n_local, 50)):
                el = inputs_local.nth(i)
                try:
                    elem_id = el.get_attribute('id') or f'field_{len(form_elements) + i}'
                    # Skip if already collected (avoid redundant processing)
                    if elem_id in form_elements:
                        continue
                    
                    tag = (el.evaluate("e => e.tagName") or '').lower()
                    typ = el.get_attribute('type') or ('select' if tag == 'select' else 'text')
                    name = el.get_attribute('name') or ''
                    label = ''
                    if elem_id:
                        lab = dlg_local.locator(f'label[for="{elem_id}"]').first
                        if lab.count() > 0:
                            label = (lab.inner_text() or '').strip()
                    if not label:
                        try:
                            label = (el.evaluate("e => e.closest('label')?.innerText || ''") or '').strip()
                        except Exception:
                            label = ''
                    question = {
                        'id': elem_id,
                        'type': typ,
                        'name': name,
                        'label': label,
                    }
                    if tag == 'select':
                        opts = el.locator('option')
                        options = []
                        # Reduced from 100 to 50 options
                        for j in range(min(opts.count(), 50)):
                            oj = opts.nth(j)
                            options.append({'value': oj.get_attribute('value'), 'text': (oj.inner_text() or '').strip()})
                        question['options'] = options
                    sel = _sel_for_id(elem_id) if elem_id else None
                    form_elements[elem_id] = {**question, **({"selector": sel} if sel else {})}
                    questions.append(question)
                except Exception:
                    continue

        # Collect current step
        collect_inputs_from_dialog(dlg)

        # Traverse steps to collect more
        profile = {
            "email": os.getenv("PROFILE_EMAIL") or os.getenv("LINKEDIN_USERNAME"),
            "phone": os.getenv("PROFILE_PHONE"),
            "phone_country": os.getenv("PROFILE_PHONE_COUNTRY") or "United States (+1)",
        }
        
        # DYNAMIC DETECTION: Try to detect actual number of steps from the form
        detected_steps = None
        try:
            # Wait a bit for step indicators to render
            time.sleep(0.2)  # Reduced from 0.3
            step_info = _detect_step_info(dlg)
            if step_info and step_info.get("total"):
                detected_steps = step_info["total"]
                print(f"[Form Detection] ✓ Detected {detected_steps} total steps (Progress: {step_info.get('progress', 0)}%)")
            else:
                print(f"[Form Detection] Could not detect step count - step_info: {step_info}")
        except Exception as e:
            print(f"[Form Detection] Detection error: {e}")
        
        # Use detected steps if available, otherwise fall back to environment or defaults
        max_steps_env = os.getenv("SNAPSHOT_STEPS_MAX")
        try:
            if detected_steps and detected_steps > 0:
                # Use detected steps EXACTLY (no need for safety cap if detected properly)
                max_steps = detected_steps
                print(f"[Form Detection] Using detected steps: {max_steps}")
            elif max_steps_env:
                max_steps = int(max_steps_env)
                print(f"[Form Detection] Using env SNAPSHOT_STEPS_MAX: {max_steps}")
            else:
                # Conservative default - LinkedIn forms are usually 2-5 steps
                max_steps = 5 if FAST_SCRAPE else 8
                print(f"[Form Detection] Using default max_steps: {max_steps}")
        except Exception:
            max_steps = 5 if FAST_SCRAPE else 8
            print(f"[Form Detection] Fallback to default: {max_steps}")
        
        for step_index in range(max_steps):
            print(f"[Form Scraping] Step {step_index + 1}/{max_steps}")
            cfg_step = _build_form_config_from_dialog(dlg)
            nav_step = cfg_step.get("navigation", {})
            
            # Don't fill forms during scraping - just collect questions
            # Removed: _fill_easy_apply_dialog(page, dlg, profile)

            # Resolve Next/Review buttons and their state
            next_btn = None
            review_btn = None
            try:
                if nav_step.get("next"):
                    sel = nav_step["next"][0]["selector"]
                    next_btn = dlg.locator(sel).first if sel else dlg.get_by_role('button', name=re.compile(r"Next|Continue|Save and continue", re.I)).first
            except Exception:
                next_btn = None
            try:
                if nav_step.get("review"):
                    sel = nav_step["review"][0]["selector"]
                    review_btn = dlg.locator(sel).first if sel else dlg.get_by_role('button', name=re.compile(r"Review", re.I)).first
            except Exception:
                review_btn = None

            # Check enabled state
            def _enabled(el) -> bool:
                try:
                    return bool(el and el.count() > 0 and el.is_enabled())
                except Exception:
                    return False

            has_next = _enabled(next_btn)
            has_review = _enabled(review_btn)
            if not (has_next or has_review):
                # No further pages to traverse
                break

            clicked = False
            try:
                if has_next and next_btn is not None:
                    next_btn.click(timeout=8000)
                    clicked = True
                elif has_review and review_btn is not None:
                    review_btn.click(timeout=8000)
                    clicked = True
            except Exception:
                clicked = False

            if not clicked:
                break

            # Reduced wait time from 0.8s to 0.5s for faster traversal
            time.sleep(0.5)
            dlg = page.locator('[role="dialog"]').first
            collect_inputs_from_dialog(dlg)

        # Before closing, build answer hints and normalized schema from current dialog
        try:
            cfg_for_hints = _build_form_config_from_dialog(dlg)
            answer_hints_map: Dict[str, Any] = cfg_for_hints.get("answer_hints", {}) if isinstance(cfg_for_hints, dict) else {}
        except Exception:
            answer_hints_map = {}

        # Close modal
        try:
            dlg.get_by_role('button', name=re.compile(r"Dismiss|Cancel|Close|Discard", re.I)).first.click(timeout=5000)
            time.sleep(0.4)
            confirm = page.get_by_role('button', name=re.compile(r"Discard", re.I)).first
            if confirm.count() > 0:
                confirm.click(timeout=3000)
                time.sleep(0.3)
        except Exception:
            try:
                page.keyboard.press('Escape')
                time.sleep(0.3)
            except Exception:
                pass

        # Build a simple answer template mapping each question to a placeholder
        answer_template: Dict[str, Any] = {}
        for q in questions:
            q_type = (q.get('type') or '').lower()
            if q_type in ['radio']:
                ans_type = 'RadioSelection'
            elif q_type in ['select'] or 'options' in q:
                ans_type = 'DropdownSelection'
            elif q_type in ['checkbox']:
                ans_type = 'CheckboxState'
            elif q_type in ['textarea']:
                ans_type = 'LongTextResponse'
            elif q_type in ['file']:
                ans_type = 'FilePath'
            else:
                ans_type = 'TextResponse'
            key = q.get('id') or q.get('label') or 'unknown'
            # Attach schema extras for LLM compatibility
            ans_entry: Dict[str, Any] = {
                'id': q.get('id'),
                'name': q.get('name'),
                'label': q.get('label') or q.get('name') or q.get('id'),
                'answer_type': ans_type,
                'required': False
            }
            # Add options when present
            if 'options' in q and isinstance(q['options'], list):
                ans_entry['options'] = [opt.get('text') for opt in q['options'] if isinstance(opt, dict)]
            # Add selector if captured
            try:
                if q.get('id') and isinstance(form_elements, dict):
                    sel = form_elements.get(q['id'], {}).get('selector')
                    if sel:
                        ans_entry['selector'] = sel
            except Exception:
                pass
            # Add answer hint if available
            try:
                if q.get('id') in answer_hints_map:
                    hint = answer_hints_map[q['id']]
                    if isinstance(hint, dict) and 'suggested_value' in hint:
                        ans_entry['hint'] = hint['suggested_value']
            except Exception:
                pass
            answer_template[key] = ans_entry

        return {
            'form_elements': form_elements,
            'questions_json': questions,
            'answer_template': answer_template,
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        print(f"Easy Apply snapshot error: {e}")
        return None


def _ensure_logged_in(page, username_secret=None, password_secret=None) -> None:
    """Best-effort login using credentials (strings or Secret objects) or env variables and persistent context."""
    try:
        # If we see a sign-in wall or login form, perform login
        if any(k in (page.url or "") for k in ["/authwall", "/login"]):
            page.goto("https://www.linkedin.com/login", timeout=30000)
        # Detect login form controls
        if page.get_by_role("textbox", name=re.compile(r"Email|Phone", re.I)).count() > 0 and page.get_by_role("textbox", name=re.compile(r"Password", re.I)).count() > 0:
            # Check if credentials are passed as strings (from global variables) or as Secret objects
            if username_secret and password_secret:
                # Handle both string values and Secret objects
                if hasattr(username_secret, 'value'):
                    username = username_secret.value
                    password = password_secret.value
                else:
                    username = username_secret
                    password = password_secret
            else:
                username = LINKEDIN_USERNAME
                password = LINKEDIN_PASSWORD
                
            if not username or not password:
                return
            page.get_by_role("textbox", name=re.compile(r"Email|Phone", re.I)).fill(username)
            page.get_by_role("textbox", name=re.compile(r"Password", re.I)).fill(password)
            page.get_by_role("button", name=re.compile(r"Sign in", re.I)).first.click()
            time.sleep(4)
        # Heuristic: if nav has profile/menu, we're logged in
        # No-op otherwise; persistent context may already be authed
    except Exception:
        pass


# Helper: build a safe selector for an element id (handles special chars like parentheses)
def _sel_for_id(el_id: str) -> str:
    if not el_id:
        return ""
    # Only use #id when it contains safe characters
    if re.fullmatch(r"[A-Za-z_][-A-Za-z0-9_]*", el_id):
        return f"#{el_id}"
    # Fallback to attribute selector
    # Escape quotes in id safely
    safe = el_id.replace('"', '\\"')
    return f"[id=\"{safe}\"]"


def _build_form_config_from_dialog(dlg) -> Dict[str, Any]:
    """Create a normalized form_config for automation from an Easy Apply dialog element."""
    form_config: Dict[str, Any] = {
        "elements": {},
        "navigation": {
            "next": [],
            "back": [],
            "review": [],
            "submit": [],
            "dismiss": [],
            "discard": []
        },
        "meta": {
            "total_fields": 0,
            "required_fields": 0,
            "has_file_upload": False,
            "steps_estimate": 1
        },
        "answer_hints": {}
    }

    # Collect navigation buttons
    try:
        nav_map = {
            "next": ['button:has-text("Next")', 'button:has-text("Continue")', 'button:has-text("Save and continue")', '[aria-label*="Next"]', '[aria-label*="Continue"]'],
            "back": ['button:has-text("Back")', '[aria-label*="Back"]'],
            "review": ['button:has-text("Review")', '[aria-label*="Review"]'],
            "submit": ['button:has-text("Submit application")', 'button:has-text("Submit")', 'button[type="submit"]', 'button:has-text("Apply")'],
            "dismiss": ['button:has-text("Dismiss")', 'button:has-text("Cancel")', 'button[aria-label*="Dismiss"]'],
            "discard": ['button:has-text("Discard")']
        }
        for key, selectors in nav_map.items():
            for sel in selectors:
                try:
                    items = dlg.locator(sel)
                    for i in range(min(items.count(), 10)):
                        el = items.nth(i)
                        el_id = el.get_attribute('id') or ''
                        data_test = el.get_attribute('data-test') or ''
                        cls = (el.get_attribute('class') or '').split(' ')[0] if (el.get_attribute('class') or '') else ''
                        selector = _sel_for_id(el_id) if el_id else (f"[data-test='{data_test}']" if data_test else (f"button.{cls}" if cls else sel))
                        label = ''
                        try:
                            label = (el.inner_text() or '').strip()
                        except Exception:
                            label = key
                        form_config["navigation"][key].append({
                            "label": label,
                            "selector": selector
                        })
                except Exception:
                    continue
    except Exception:
        pass

    # Collect inputs
    try:
        inputs = dlg.locator('input, select, textarea')
        n = inputs.count()
        required_count = 0
        has_upload = False
        for i in range(min(n, 300)):
            el = inputs.nth(i)
            try:
                tag = (el.evaluate("e => e.tagName") or '').lower()
                typ = (el.get_attribute('type') or ('select' if tag == 'select' else 'text')).lower()
                el_id = el.get_attribute('id') or ''
                name = el.get_attribute('name') or ''
                aria_label = el.get_attribute('aria-label') or ''
                placeholder = el.get_attribute('placeholder') or ''
                required = (el.get_attribute('required') is not None) or (el.get_attribute('aria-required') == 'true')
                # Label resolution
                label = ''
                if el_id:
                    lab = dlg.locator(f'label[for="{el_id}"]').first
                    if lab.count() > 0:
                        label = (lab.inner_text() or '').strip()
                if not label:
                    try:
                        label = (el.evaluate("e => e.closest('label')?.innerText || ''") or '').strip()
                    except Exception:
                        label = ''
                if not label:
                    label = aria_label or placeholder or name or el_id or f'field_{i}'

                # Determine category/interaction
                if tag == 'select':
                    category = 'dropdown'
                    interaction = 'select_option'
                elif typ in ['checkbox']:
                    category = 'checkbox'
                    interaction = 'check'
                elif typ in ['radio']:
                    category = 'radio'
                    interaction = 'select'
                elif typ in ['file']:
                    category = 'file_upload'
                    interaction = 'upload_file'
                elif tag == 'textarea':
                    category = 'text_area'
                    interaction = 'type'
                else:
                    category = 'text_input'
                    interaction = 'type'

                # Build a robust selector
                cls = (el.get_attribute('class') or '').split(' ')[0] if (el.get_attribute('class') or '') else ''
                selector = _sel_for_id(el_id) if el_id else (f"[name='{name}']" if name else (f".{cls}" if cls else None))

                field: Dict[str, Any] = {
                    "id": el_id or name or f'field_{i}',
                    "tag": tag,
                    "type": typ,
                    "label": label,
                    "required": bool(required),
                    "category": category,
                    "interaction": interaction,
                    "selector": selector
                }

                # Options for select
                if category == 'dropdown':
                    opts = el.locator('option')
                    field["options"] = []
                    for j in range(min(opts.count(), 100)):
                        oj = opts.nth(j)
                        try:
                            field["options"].append({
                                "value": oj.get_attribute('value'),
                                "text": (oj.inner_text() or '').strip()
                            })
                        except Exception:
                            continue

                # Radio group options
                if category == 'radio' and name:
                    radios = dlg.locator(f'input[type="radio"][name="{name}"]')
                    field["radio_options"] = []
                    for j in range(min(radios.count(), 20)):
                        r = radios.nth(j)
                        try:
                            r_id = r.get_attribute('id') or ''
                            r_label = ''
                            if r_id:
                                lab = dlg.locator(f'label[for="{r_id}"]').first
                                if lab.count() > 0:
                                    r_label = (lab.inner_text() or '').strip()
                            field["radio_options"].append({
                                "value": r.get_attribute('value') or '',
                                "label": r_label
                            })
                        except Exception:
                            continue

                # Answer hints
                hint = None
                lower = label.lower()
                if any(k in lower for k in ["email"]):
                    hint = "{{profile.email}}"
                elif any(k in lower for k in ["phone country code", "country code"]):
                    hint = "{{profile.phone_country}}"
                elif any(k in lower for k in ["phone", "mobile", "tel"]):
                    hint = "{{profile.phone}}"
                elif any(k in lower for k in ["work authorization", "authorized to work", "legally authorized", "sponsorship", "visa"]):
                    hint = "{{profile.work_authorization}}"
                elif "first name" in lower:
                    hint = "{{profile.first_name}}"
                elif any(k in lower for k in ["last name", "surname"]):
                    hint = "{{profile.last_name}}"
                elif any(k in lower for k in ["linkedin", "profile url"]):
                    hint = "{{profile.linkedin_url}}"
                elif any(k in lower for k in ["website", "portfolio", "url"]):
                    hint = "{{profile.website}}"
                if hint:
                    form_config["answer_hints"][field["id"]] = {
                        "label": label,
                        "suggested_value": hint
                    }

                form_config["elements"][field["id"]] = field
                if required:
                    required_count += 1
                if category == 'file_upload':
                    has_upload = True

            except Exception:
                continue

        form_config["meta"]["total_fields"] = len(form_config["elements"]) 
        form_config["meta"]["required_fields"] = required_count
        form_config["meta"]["has_file_upload"] = has_upload
        steps = 1
        if form_config["navigation"]["next"]:
            steps = len(form_config["navigation"]["next"]) + 1
        form_config["meta"]["steps_estimate"] = steps
    except Exception:
        pass

    return form_config


def _fill_easy_apply_dialog(page, dlg, profile: Dict[str, Any], answers: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Fill common Easy Apply fields using heuristics, provided profile, and arbitrary answers.

    profile keys supported:
      - email: str
      - phone: str (national number without country code preferred)
      - phone_country: str (e.g., "United States (+1)")

    answers mapping supported (any number):
      - keys may be field id, name, or label; matching is case-insensitive and normalized.
      - values: for text/textarea -> str/number; dropdown/radio -> label or value; checkbox -> bool; file_upload -> path.

    Returns a dict with details: { filled: int, required: int, missing: [labels] }
    """
    summary = {"filled": 0, "required": 0, "missing": []}

    def norm_key(s: str) -> str:
        import re as _re
        return _re.sub(r"[^a-z0-9]+", "", (s or "").lower())

    def id_locator(dlg_local, fid: str):
        sel = _sel_for_id(fid)
        return dlg_local.locator(sel).first if sel else None

    answers_dict: Dict[str, Any] = answers or {}
    # Build normalized lookup: exact and normalized labels
    normalized_answers: Dict[str, Any] = {}
    for k, v in answers_dict.items():
        if isinstance(k, str):
            normalized_answers[k] = v
            normalized_answers[norm_key(k)] = v

    try:
        cfg = _build_form_config_from_dialog(dlg)
        summary["required"] = cfg.get("meta", {}).get("required_fields", 0)

        elements: Dict[str, Any] = cfg.get("elements", {})
        for fid, field in elements.items():
            try:
                label = (field.get("label") or "").strip()
                category = field.get("category")
                selector = field.get("selector")
                required = bool(field.get("required"))

                el = None
                if selector:
                    el = dlg.locator(selector).first
                if (not el) or el.count() == 0:
                    fid_attr = field.get("id")
                    if fid_attr:
                        el = id_locator(dlg, fid_attr)
                if (not el) or el.count() == 0:
                    continue

                lower = label.lower()

                # Resolve provided answer for this field, by id/name/label, with fuzzy fallback
                provided = None
                candidates = [
                    field.get("id") or "",
                    field.get("type") or "",
                    field.get("tag") or "",
                    field.get("label") or "",
                    field.get("name") or "",
                ]
                for key in candidates:
                    if key in normalized_answers:
                        provided = normalized_answers[key]
                        break
                    nk = norm_key(key)
                    if nk and nk in normalized_answers:
                        provided = normalized_answers[nk]
                        break
                if provided is None and normalized_answers:
                    # fuzzy: if any answer key is substring of label
                    for ak, av in normalized_answers.items():
                        if not isinstance(ak, str) or len(ak) < 2:
                            continue
                        if ak == norm_key(field.get("id") or ""):
                            continue
                        if ak in norm_key(label):
                            provided = av
                            break

                # Apply provided answers first
                if provided is not None:
                    try:
                        if category == "text_input" or category == "text_area":
                            el.fill(str(provided))
                            summary["filled"] += 1
                            continue
                        if category == "dropdown":
                            # Try by label match, then by value
                            try:
                                el.select_option(label=str(provided))
                            except Exception:
                                try:
                                    el.select_option(value=str(provided))
                                except Exception:
                                    # last resort: pick first non-placeholder if required
                                    if required:
                                        options = el.locator('option')
                                        for j in range(min(options.count(), 100)):
                                            oj = options.nth(j)
                                            text = (oj.inner_text() or '').strip()
                                            if text and "select an option" not in text.lower():
                                                val = oj.get_attribute('value') or None
                                                if val:
                                                    el.select_option(value=val)
                                                    break
                            summary["filled"] += 1
                            continue
                        if category == "radio":
                            # Click radio whose label matches substring of provided
                            target = str(provided).lower()
                            radios = dlg.locator('input[type="radio"]').all()
                            clicked = False
                            for r in radios:
                                try:
                                    rid = r.get_attribute('id') or ''
                                    rlab = ''
                                    if rid:
                                        lab = dlg.locator(f'label[for="{rid}"]').first
                                        if lab.count() > 0:
                                            rlab = (lab.inner_text() or '').strip()
                                    if target in rlab.lower():
                                        r.check()
                                        clicked = True
                                        break
                                except Exception:
                                    continue
                            if not clicked and radios:
                                # fallback by value
                                for r in radios:
                                    try:
                                        if (r.get_attribute('value') or '').lower() == target:
                                            r.check()
                                            clicked = True
                                            break
                                    except Exception:
                                        continue
                            if clicked:
                                summary["filled"] += 1
                                continue
                        if category == "checkbox":
                            val = bool(provided)
                            try:
                                if val:
                                    el.check()
                                else:
                                    el.uncheck()
                            except Exception:
                                pass
                            # optional; not counted as required
                            continue
                        if category == "file_upload":
                            path = str(provided)
                            try:
                                el.set_input_files(path)
                                summary["filled"] += 1
                                continue
                            except Exception:
                                pass
                    except Exception:
                        # fall through to heuristics
                        pass

                # Heuristic fills (email/phone/country, follow checkbox, work auth/sponsorship)
                if category == "dropdown":
                    if "email" in lower and profile.get("email"):
                        try:
                            el.select_option(label=profile["email"])
                            summary["filled"] += 1
                            continue
                        except Exception:
                            pass
                    if any(k in lower for k in ["phone country code", "country code"]) and profile.get("phone_country"):
                        try:
                            el.select_option(label=profile["phone_country"])  
                            summary["filled"] += 1
                            continue
                        except Exception:
                            pass
                    if required:
                        try:
                            options = el.locator('option')
                            for j in range(min(options.count(), 100)):
                                oj = options.nth(j)
                                text = (oj.inner_text() or '').strip()
                                if text and "select an option" not in text.lower():
                                    val = oj.get_attribute('value') or None
                                    if val:
                                        el.select_option(value=val)
                                        summary["filled"] += 1
                                        break
                        except Exception:
                            pass

                elif category == "text_input":
                    if any(k in lower for k in ["phone"]) and profile.get("phone"):
                        try:
                            el.fill(str(profile["phone"]))
                            summary["filled"] += 1
                        except Exception:
                            pass

                elif category == "checkbox":
                    try:
                        # Uncheck follow company by default
                        if el.is_checked():
                            el.uncheck()
                    except Exception:
                        pass

                elif category == "radio":
                    try:
                        label_l = (label or "").lower()
                        def click_radio_with_text(preferred_labels: List[str]) -> bool:
                            opts = dlg.locator('input[type="radio"]').all()
                            for r in opts:
                                try:
                                    rid = r.get_attribute('id') or ''
                                    rlab = ''
                                    if rid:
                                        lab = dlg.locator(f'label[for="{rid}"]').first
                                        if lab.count() > 0:
                                            rlab = (lab.inner_text() or '').strip()
                                    txt = rlab.lower()
                                    if any(p in txt for p in preferred_labels):
                                        r.check()
                                        return True
                                except Exception:
                                    continue
                            return False
                        if any(k in label_l for k in ["authorized", "work authorization", "legally authorized", "eligible to work"]):
                            if click_radio_with_text(["yes", "i am authorized", "i am legally authorized"]):
                                summary["filled"] += 1
                                continue
                        if any(k in label_l for k in ["sponsorship", "require sponsorship", "visa sponsorship", "need sponsorship"]):
                            if click_radio_with_text(["no", "i do not require", "no sponsorship"]):
                                summary["filled"] += 1
                                continue
                    except Exception:
                        pass

                # Ignore file uploads unless required (left for future handling)
            except Exception:
                continue

        return summary
    except Exception:
        return summary




def configure_browser(headless_mode: bool = False):
    """Configure browser with optimized settings for both headless and headed modes.
    
    Args:
        headless_mode: Whether to run in headless mode (default: False)
    """
    # Note: robocorp.browser doesn't support all playwright options directly
    # We configure what we can and rely on Dockerfile ENV vars for the rest
    browser.configure(
        screenshot="only-on-failure",
        headless=headless_mode,
        persistent_context_directory=os.path.join(os.getcwd(), "browser_context"),
        browser_engine="chromium",  # Explicitly use chromium
    )



def extract_job_data(page, job_element, run_id: str) -> Optional[LinkedInJob]:
    """Extract structured data from a job element using unified extraction tools"""
    try:
        # Click job to load details
        job_element.click()
        time.sleep(1)
        
        # Use unified extraction tools with context='card'
        title = extract_job_title(job_element, context='card')
        company = extract_company_name(job_element, context='card', existing_title=title)
        location = extract_location_data(job_element, context='card')
        job_url, job_id = extract_job_url_and_id(job_element, existing_title=title)
        easy_apply = detect_easy_apply_availability(job_element, context='card')
        compensation = extract_compensation_data(job_element, context='card')
        status = extract_application_status(job_element, context='card')
        metadata = extract_job_metadata(page, context='card')  # Uses page for detail panel
        
        # Capture form snapshot if Easy Apply
        form_snapshot_data = None
        if easy_apply:
            form_snapshot_data = capture_form_snapshot(page, job_url)
        
        # Create job object
        job = LinkedInJob(
            title=title,
            company=company,
            job_id=job_id,
            job_url=job_url,
            
            # Location data
            location_raw=location["raw_location"],
            location_city=location["city"],
            location_state=location["state"],
            location_country=location["country"],
            location_type=location["location_type"],
            
            # Application data
            easy_apply=easy_apply,
            is_viewed=status["is_viewed"],
            applicant_count=status["applicant_count"],
            status_message=status["status_message"],
            promoted_by_hirer=status["promoted_by_hirer"],
            
            # Compensation data
            salary_range=compensation["salary_range"],
            benefits=compensation["benefits"],
            compensation_raw=compensation["raw_compensation"],
            
            # Metadata
            date_posted=metadata["date_posted"],
            job_type=metadata["job_type"],
            verified_company=metadata["verified_company"],
            
            # Form data
            form_snapshot_url=form_snapshot_data["snapshot_url"] if form_snapshot_data else "",
            form_elements=form_snapshot_data["form_elements"] if form_snapshot_data else {},
            questions_json=(json.dumps(form_snapshot_data["questions_json"]) if (form_snapshot_data and form_snapshot_data.get("questions_json") is not None) else None),
            answer_template=(json.dumps(form_snapshot_data["answer_template"]) if (form_snapshot_data and form_snapshot_data.get("answer_template") is not None) else None),
            
            # Tracking
            run_id=run_id
            # Note: raw_html is commented out in the model
        )
        
        return job
        
    except Exception as e:
        print(f"Error extracting job data: {e}")
        return None


def capture_form_snapshot(page, job_url: str) -> Optional[Dict[str, Any]]:
    """Capture Easy Apply form structure for automation"""
    try:
        # Click Easy Apply button to open form
        try:
            # Try different selectors for Easy Apply button
            easy_apply_btn = None
            
            # Try the button role selector (most reliable based on investigation)
            easy_apply_candidates = page.get_by_role("button").filter(has_text="Easy Apply").all()
            if easy_apply_candidates:
                easy_apply_btn = easy_apply_candidates[0]
            
            # Fallback to generic locator if role doesn't work
            if not easy_apply_btn:
                easy_apply_btn = page.locator('button:has-text("Easy Apply")').first
            
            if easy_apply_btn and easy_apply_btn.count() > 0:
                easy_apply_btn.click(timeout=10000)  # 10 second timeout
                time.sleep(2)
            else:
                # If Easy Apply button not found, return basic data
                return {
                    "snapshot_url": job_url,
                    "form_elements": {},
                    "questions_json": {},
                    "navigation_info": {"has_next_button": False, "has_submit_button": False, "estimated_steps": 0},
                    "robot_config": {"total_fields": 0, "required_fields": 0, "field_types": [], "has_file_upload": False, "multi_step": False},
                    "timestamp": datetime.now().isoformat(),
                    "answer_template": {}
                }
        except Exception as e:
            print(f"Could not click Easy Apply button: {e}")
            return {
                "snapshot_url": job_url,
                "form_elements": {},
                "questions_json": {},
                "navigation_info": {"has_next_button": False, "has_submit_button": False, "estimated_steps": 0},
                "robot_config": {"total_fields": 0, "required_fields": 0, "field_types": [], "has_file_upload": False, "multi_step": False},
                "timestamp": datetime.now().isoformat(),
                "answer_template": {}
            }
        
        # Capture comprehensive form configuration for robot automation
        form_elements = {}
        questions_json = {}
        navigation_info = {}
        
        # Look for multi-step form navigation
        try:
            next_buttons = page.locator('button:has-text("Next"), button[aria-label*="Next"]').all()
            submit_buttons = page.locator('button:has-text("Submit"), button[type="submit"], button:has-text("Apply")').all()
            
            navigation_info = {
                "has_next_button": len(next_buttons) > 0,
                "has_submit_button": len(submit_buttons) > 0,
                "estimated_steps": len(next_buttons) + 1 if next_buttons else 1
            }
        except Exception:
            navigation_info = {"has_next_button": False, "has_submit_button": True, "estimated_steps": 1}
        
        # Enhanced form element capture with comprehensive field mapping
        try:
            # Capture all interactive elements
            all_elements = page.locator('input, select, textarea, button, [role="button"], [role="checkbox"], [role="radio"], [role="combobox"]').all()
            
            for i, elem in enumerate(all_elements):
                    try:
                        # Get basic attributes
                        elem_id = elem.get_attribute('id') or f"element_{i}"
                        elem_type = elem.get_attribute('type') or elem.tag_name.lower()
                        elem_name = elem.get_attribute('name') or ""
                        elem_role = elem.get_attribute('role') or ""
                        elem_class = elem.get_attribute('class') or ""
                        
                        # Determine field category and interaction type
                        field_category = "unknown"
                        interaction_type = "click"
                        
                        # Classify field types for robot automation
                        if elem_type in ['text', 'email', 'tel', 'url']:
                            field_category = "text_input"
                            interaction_type = "type"
                        elif elem_type in ['password']:
                            field_category = "password_input"
                            interaction_type = "type"
                        elif elem_type in ['number', 'range']:
                            field_category = "numeric_input"
                            interaction_type = "type"
                        elif elem_type in ['checkbox'] or elem_role == 'checkbox':
                            field_category = "checkbox"
                            interaction_type = "check"
                        elif elem_type in ['radio'] or elem_role == 'radio':
                            field_category = "radio_button"
                            interaction_type = "select"
                        elif elem_type == 'select' or elem_role == 'combobox':
                            field_category = "dropdown"
                            interaction_type = "select_option"
                        elif elem_type == 'file':
                            field_category = "file_upload"
                            interaction_type = "upload_file"
                        elif elem_type == 'textarea':
                            field_category = "text_area"
                            interaction_type = "type"
                        elif elem_type == 'button' or elem_role == 'button':
                            field_category = "button"
                            interaction_type = "click"
                        
                        # Try to find associated label or context
                        label_text = ""
                        question_text = ""
                        try:
                            # Multiple label detection strategies
                            label_elem = None
                            
                            # Strategy 1: Direct label association
                            if elem_id:
                                label_elem = page.locator(f'label[for="{elem_id}"]').first
                                if label_elem.count() > 0:
                                    label_text = label_elem.inner_text().strip()
                            
                            # Strategy 2: Parent container label
                            if not label_text:
                                parent = elem.locator('xpath=..')
                                parent_label = parent.locator('label').first
                                if parent_label.count() > 0:
                                    label_text = parent_label.inner_text().strip()
                            
                            # Strategy 3: Preceding sibling label
                            if not label_text:
                                preceding_label = elem.locator('xpath=preceding-sibling::label[1]')
                                if preceding_label.count() > 0:
                                    label_text = preceding_label.inner_text().strip()
                            
                            # Strategy 4: aria-label or placeholder
                            if not label_text:
                                label_text = elem.get_attribute('aria-label') or elem.get_attribute('placeholder') or ""
                            
                            # Extract question context for better understanding
                            question_container = elem.locator('xpath=ancestor::*[contains(@class, "question") or contains(@class, "field") or contains(@class, "form-group")][1]')
                            if question_container.count() > 0:
                                question_text = question_container.inner_text().strip()[:200]  # Limit length
                                
                        except Exception:
                            pass
                        
                        # Build comprehensive field configuration
                        field_config = {
                            "id": elem_id,
                            "type": elem_type,
                            "name": elem_name,
                            "role": elem_role,
                            "class": elem_class,
                            "label": label_text,
                            "question_context": question_text,
                            "field_category": field_category,
                            "interaction_type": interaction_type,
                            "required": elem.get_attribute('required') is not None or 'required' in elem_class,
                            "visible": elem.is_visible(),
                            "enabled": elem.is_enabled(),
                            "selector": f"#{elem_id}" if elem_id else f"[name='{elem_name}']" if elem_name else f".{elem_class.split()[0]}" if elem_class else None
                        }
                        
                        # Enhanced option capture for select elements
                        if field_category == "dropdown":
                            try:
                                options = elem.locator('option').all()
                                field_config["options"] = [
                                    {
                                        "value": opt.get_attribute('value') or "",
                                        "text": opt.inner_text().strip(),
                                        "selected": opt.get_attribute('selected') is not None
                                    }
                                    for opt in options
                                ]
                            except Exception:
                                field_config["options"] = []
                        
                        # For radio button groups, capture all options
                        if field_category == "radio_button" and elem_name:
                            try:
                                radio_group = page.locator(f'input[name="{elem_name}"]').all()
                                field_config["radio_options"] = []
                                for radio in radio_group:
                                    radio_label = ""
                                    radio_id = radio.get_attribute('id')
                                    if radio_id:
                                        radio_label_elem = page.locator(f'label[for="{radio_id}"]').first
                                        if radio_label_elem.count() > 0:
                                            radio_label = radio_label_elem.inner_text().strip()
                                    
                                    field_config["radio_options"].append({
                                        "value": radio.get_attribute('value') or "",
                                        "label": radio_label,
                                        "checked": radio.is_checked()
                                    })
                            except Exception:
                                field_config["radio_options"] = []
                        
                        # File upload specific handling
                        if field_category == "file_upload":
                            field_config["accept"] = elem.get_attribute('accept') or ""
                            field_config["multiple"] = elem.get_attribute('multiple') is not None
                            
                            # Detect if this is resume upload based on context
                            if any(keyword in label_text.lower() for keyword in ['resume', 'cv', 'curriculum']):
                                field_config["file_type"] = "resume"
                            elif any(keyword in label_text.lower() for keyword in ['cover', 'letter']):
                                field_config["file_type"] = "cover_letter"
                            else:
                                field_config["file_type"] = "document"
                        
                        # Generate question mapping for AI processing
                        if label_text and field_category not in ["button"]:
                            # Create standardized question key
                            question_key = label_text.replace(' ', '').replace('?', '').replace(':', '')
                            
                            # Map common field types to expected answers
                            answer_template = None
                            if field_category == "text_input":
                                if any(keyword in label_text.lower() for keyword in ['email', 'e-mail']):
                                    answer_template = "EmailAddress"
                                elif any(keyword in label_text.lower() for keyword in ['phone', 'mobile', 'tel']):
                                    answer_template = "PhoneNumber"
                                elif any(keyword in label_text.lower() for keyword in ['first name', 'firstname']):
                                    answer_template = "FirstName"
                                elif any(keyword in label_text.lower() for keyword in ['last name', 'lastname', 'surname']):
                                    answer_template = "LastName"
                                elif any(keyword in label_text.lower() for keyword in ['linkedin', 'profile']):
                                    answer_template = "LinkedInProfile"
                                elif any(keyword in label_text.lower() for keyword in ['website', 'portfolio', 'url']):
                                    answer_template = "Website"
                                else:
                                    answer_template = "TextResponse"
                            elif field_category == "dropdown":
                                answer_template = "DropdownSelection"
                            elif field_category == "radio_button":
                                answer_template = "RadioSelection"
                            elif field_category == "checkbox":
                                answer_template = "CheckboxState"
                            elif field_category == "text_area":
                                answer_template = "LongTextResponse"
                            elif field_category == "file_upload":
                                answer_template = "FilePath"
                            
                            if answer_template:
                                questions_json[question_key] = {
                                    "question": label_text,
                                    "field_id": elem_id,
                                    "answer_type": answer_template,
                                    "field_category": field_category,
                                    "interaction_type": interaction_type,
                                    "required": field_config["required"]
                                }
                                
                                # Add options for selection fields
                                if field_category == "dropdown" and "options" in field_config:
                                    questions_json[question_key]["available_options"] = [opt["text"] for opt in field_config["options"]]
                                elif field_category == "radio_button" and "radio_options" in field_config:
                                    questions_json[question_key]["available_options"] = [opt["label"] for opt in field_config["radio_options"]]
                        
                        form_elements[elem_id] = field_config
                            
                    except Exception as e:
                        print(f"Error capturing form element {i}: {e}")
                        continue
                        
        except Exception as e:
            print(f"Error accessing form inputs: {e}")
            form_elements = {}
            questions_json = {}
        
        # Close the form - try multiple methods based on actual LinkedIn structure
        try:
                # Look for the Dismiss button in the Easy Apply dialog
                dismiss_btn = page.get_by_role("button", name="Dismiss").first
                if dismiss_btn.count() > 0:
                    dismiss_btn.click(timeout=5000)
                    time.sleep(1)
                    
                    # Check if save dialog appears and handle it
                    try:
                        # Wait a moment for save dialog to appear
                        time.sleep(1)
                        discard_btn = page.get_by_role("button", name="Discard").first
                        if discard_btn.count() > 0:
                            discard_btn.click(timeout=5000)
                            time.sleep(1)
                    except Exception:
                        pass
                else:
                    # Fallback: try Escape key
                    page.keyboard.press("Escape")
                    time.sleep(1)
        except Exception:
            try:
                # Final fallback: try old selector
                close_btn = page.locator('button[aria-label*="Dismiss"], button:has-text("Cancel")').first
                if close_btn.count() > 0:
                    close_btn.click(timeout=5000)
                    time.sleep(1)
            except Exception:
                # If all else fails, just continue
                pass
        
        return {
            "snapshot_url": job_url,
            "form_elements": form_elements,
            "questions_json": questions_json,
            "navigation_info": navigation_info,
            "robot_config": {
                "total_fields": len(form_elements),
                "required_fields": len([f for f in form_elements.values() if f.get("required", False)]),
                "field_types": list(set(f.get("field_category", "unknown") for f in form_elements.values())),
                "has_file_upload": any(f.get("field_category") == "file_upload" for f in form_elements.values()),
                "multi_step": navigation_info.get("has_next_button", False)
            },
            "timestamp": datetime.now().isoformat(),
            "answer_template": {
                question_key: {
                    "answer": f"<<ANSWER_FOR_{q_info['answer_type']}_HERE>>",
                    "confidence": 1.0,
                    "reasoning": "Generated by AI agent"
                }
                for question_key, q_info in questions_json.items()
            }
        }
            
    except Exception as e:
        print(f"Error capturing form snapshot: {e}")
        return None

