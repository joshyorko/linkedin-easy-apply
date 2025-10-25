from typing import Optional, Dict, Any, List, Set
import dotenv
import os
from robocorp import browser
import time
import re

from .tools import _sel_for_id, parse_location



dotenv.load_dotenv()


LINKEDIN_USERNAME = os.getenv("LINKEDIN_USERNAME")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD")


STATE_ABBREV_TO_NAME: Dict[str, str] = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
}

STATE_NAME_TO_ABBREV: Dict[str, str] = {v.lower(): k for k, v in STATE_ABBREV_TO_NAME.items()}

LOCATION_PENALTY_KEYWORDS = (
    "county",
    "historic",
    "district",
    "metropolitan",
    "metro area",
    "region",
    "borough",
)


def _desired_location_strings(context: Dict[str, Optional[str]]) -> List[str]:
    """Return preferred renderings for the user's location."""
    city = (context.get("city") or "").strip()
    state_full = (context.get("state_full") or "").strip()
    state_abbrev = (context.get("state_abbrev") or "").strip()
    country = (context.get("country") or "").strip()

    strings: List[str] = []
    if city and state_abbrev:
        strings.append(f"{city}, {state_abbrev}")
    if city and state_full:
        strings.append(f"{city}, {state_full}")
    if city and state_full and country:
        strings.append(f"{city}, {state_full}, {country}")
    if city and state_abbrev and country:
        strings.append(f"{city}, {state_abbrev}, {country}")
    if city and country and country.lower() == "united states":
        strings.append(f"{city}, {state_full}, United States")
        strings.append(f"{city}, {state_abbrev}, United States")
    if city and not strings:
        strings.append(city)
    if state_full and not city:
        strings.append(state_full)
    if state_abbrev and not city:
        strings.append(state_abbrev)
    deduped: List[str] = []
    seen: Set[str] = set()
    for s in strings:
        s_clean = s.strip()
        if not s_clean:
            continue
        key = s_clean.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(s_clean)
    return deduped

def _ensure_logged_in(page) -> None:
    """Best-effort login using environment credentials and persistent context."""
    try:
        # If we see a sign-in wall or login form, perform login
        if any(k in (page.url or "") for k in ["/authwall", "/login"]):
            page.goto("https://www.linkedin.com/login", timeout=30000)
        # Detect login form controls
        if page.get_by_role("textbox", name=re.compile(r"Email|Phone", re.I)).count() > 0 and page.get_by_role("textbox", name=re.compile(r"Password", re.I)).count() > 0:
            # Use environment variables for credentials
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





def configure_browser(headless_mode: bool = False):
    browser.configure(
        screenshot="on",
        headless=headless_mode,
        persistent_context_directory=os.path.join(os.getcwd(), "browser_context"),

    )


def _looks_like_location_field(label: str, field_id: str, extra: Optional[str] = None) -> bool:
    """Heuristic to detect location inputs while avoiding relocation questions."""
    parts = [label or "", field_id or "", extra or ""]
    text = " ".join(parts).strip().lower()
    if not text:
        return False
    if "relocation" in text:
        return False
    return (" location" in f" {text}" or " city" in f" {text}")


def _prepare_location_context(target_text: str, profile: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Build normalized city/state/country context from provided text and profile fallbacks."""
    profile = profile or {}
    info = parse_location(target_text)

    profile_location = profile.get("location") or ""
    if profile_location and (not info.get("city") or not info.get("state") or not info.get("country")):
        fallback = parse_location(profile_location)
        for key in ("city", "state", "country"):
            if not info.get(key) and fallback.get(key):
                info[key] = fallback.get(key)

    if not info.get("city") and profile.get("address_city"):
        info["city"] = profile.get("address_city")
    if not info.get("state") and profile.get("address_state"):
        info["state"] = profile.get("address_state")
    if not info.get("country") and profile.get("address_country"):
        info["country"] = profile.get("address_country")

    state_raw = (info.get("state") or "").strip()
    state_abbrev: Optional[str] = None
    state_full: Optional[str] = None
    if state_raw:
        if len(state_raw) == 2 and state_raw.upper() in STATE_ABBREV_TO_NAME:
            state_abbrev = state_raw.upper()
            state_full = STATE_ABBREV_TO_NAME[state_abbrev]
        else:
            state_full = state_raw.title()
            state_abbrev = STATE_NAME_TO_ABBREV.get(state_raw.lower())
            if not state_full:
                state_full = state_raw

    country = (info.get("country") or "").strip()
    if not country and state_abbrev in STATE_ABBREV_TO_NAME:
        country = "United States"

    return {
        "raw": target_text,
        "city": (info.get("city") or "").strip(),
        "state_abbrev": state_abbrev,
        "state_full": state_full,
        "country": country,
    }


def _collect_typeahead_options(page, dlg, max_options: int = 20) -> List[Dict[str, Any]]:
    """Collect visible options for the currently open typeahead dropdown."""
    selectors = [
        '[role="listbox"] [role="option"]',
        '[role="option"]',
        '.artdeco-typeahead__dropdown [role="option"]',
        '.artdeco-typeahead__dropdown li',
        '.typeahead-dropdown__item',
    ]
    options: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    for sel in selectors:
        for scope in (dlg, page):
            try:
                loc = scope.locator(sel)
            except Exception:
                continue
            try:
                count = min(loc.count(), max_options)
            except Exception:
                continue
            for idx in range(count):
                try:
                    opt = loc.nth(idx)
                    text = (opt.inner_text() or '').strip()
                    key = text.lower()
                    if not text or key in seen:
                        continue
                    options.append({"locator": opt, "text": text})
                    seen.add(key)
                    if len(options) >= max_options:
                        return options
                except Exception:
                    continue
    return options


def _score_location_option(text: str, context: Dict[str, Optional[str]]) -> int:
    """Score an option text against the desired city/state/country."""
    text_lower = text.lower()
    score = 0
    city = (context.get("city") or "").lower()
    state_full = (context.get("state_full") or "").lower()
    state_abbrev = (context.get("state_abbrev") or "").lower()
    country = (context.get("country") or "").lower()

    desired_strings = [s.lower() for s in _desired_location_strings(context)]

    if desired_strings:
        for desired in desired_strings:
            if text_lower == desired:
                score += 12
                break
            if text_lower.startswith(desired):
                score += 7
                break

    if city and city in text_lower:
        score += 3
    if state_full and state_full in text_lower:
        score += 3
    if state_abbrev and state_abbrev in text_lower:
        score += 2
    if country and country in text_lower:
        score += 1

    for penalty in LOCATION_PENALTY_KEYWORDS:
        if penalty in text_lower:
            score -= 6
            break
    return score


def _location_value_matches(context: Dict[str, Optional[str]], value: Optional[str]) -> bool:
    """Return True when the rendered input value looks like the desired location."""
    val = (value or "").strip().lower()
    if not val:
        return False

    desired_strings = [s.lower() for s in _desired_location_strings(context)]
    if desired_strings and val in desired_strings:
        return True

    # Reject obvious false positives containing penalty keywords unless we have no other info
    for penalty in LOCATION_PENALTY_KEYWORDS:
        if penalty in val:
            return False

    city = (context.get("city") or "").strip().lower()
    state_full = (context.get("state_full") or "").strip().lower()
    state_abbrev = (context.get("state_abbrev") or "").strip().lower()

    if city and city not in val:
        return False

    if state_full:
        if state_full not in val:
            if state_abbrev and state_abbrev not in val:
                return False
    elif state_abbrev:
        if state_abbrev not in val:
            return False

    country = (context.get("country") or "").strip().lower()
    if country and country not in val:
        # Country mismatch is informative but not fatal for US-localized inputs.
        # Allow if the value already includes city/state.
        if city and ((state_full and state_full in val) or (state_abbrev and state_abbrev in val)):
            return True
        return False

    return True


def _fill_location_typeahead(page, dlg, element, target_text: str, profile: Dict[str, Any]) -> bool:
    """Fill a location field and select the best matching suggestion from the dropdown."""
    target_text = (target_text or '').strip()
    if not target_text:
        return False

    context = _prepare_location_context(target_text, profile)

    input_candidates: List[str] = []
    city = context.get("city")
    state_abbrev = context.get("state_abbrev")
    state_full = context.get("state_full")

    if city and state_abbrev:
        input_candidates.append(f"{city}, {state_abbrev}")
    if city and state_full:
        formatted = f"{city}, {state_full}"
        if formatted not in input_candidates:
            input_candidates.append(formatted)
    if city and not input_candidates:
        input_candidates.append(city)
    if state_full and not input_candidates:
        input_candidates.append(state_full)
    if target_text not in input_candidates:
        input_candidates.append(target_text)

    for candidate in input_candidates:
        try:
            element.click(timeout=2000)
        except Exception:
            pass
        try:
            element.fill('')
            time.sleep(0.1)
        except Exception:
            try:
                element.press('Control+A')
                element.press('Delete')
            except Exception:
                pass
        try:
            if len(candidate) <= 24:
                element.type(candidate, delay=40)
            else:
                element.type(candidate)
        except Exception:
            try:
                element.fill(candidate)
            except Exception:
                continue

        time.sleep(0.3)
        options: List[Dict[str, Any]] = []
        for attempt in range(5):
            options = _collect_typeahead_options(page, dlg)
            if options:
                break
            time.sleep(0.2)

        if not options:
            continue

        desired_strings = [s.lower() for s in _desired_location_strings(context)]
        best_option = None
        best_score = -999
        desired_combo = None
        if city and state_full:
            desired_combo = f"{city}, {state_full}".lower()

        # First, look for perfect match with desired strings.
        for opt in options:
            text_lower = opt["text"].strip().lower()
            if text_lower in desired_strings:
                best_option = opt
                best_score = 999
                break

        if not best_option:
            for opt in options:
                text = opt["text"]
                score = _score_location_option(text, context)
                if desired_combo and text.lower().startswith(desired_combo):
                    score += 2
                if score > best_score or (score == best_score and best_option and len(text) < len(best_option["text"])):
                    best_score = score
                    best_option = opt

        if not best_option:
            best_option = options[0]

        try:
            print(f"[Location] Selecting '{best_option['text']}' for location field")
            best_option["locator"].click(timeout=2000, force=False)
            time.sleep(0.2)
            try:
                element.evaluate("el => el.blur()")
            except Exception:
                pass
            # Confirm the input now reflects the desired city/state; retry otherwise.
            matched = False
            for _ in range(8):
                try:
                    current_value = element.input_value()
                except Exception:
                    try:
                        current_value = element.evaluate("el => el.value")
                    except Exception:
                        current_value = ""
                if _location_value_matches(context, current_value):
                    matched = True
                    break
                time.sleep(0.2)
            if matched:
                print(f"[Location] ✓ Confirmed location value '{current_value}'")
                try:
                    element.press('Enter')
                except Exception:
                    pass
                return True
            print(f"[Location] ⚠️ Value mismatch after selecting option: '{current_value}'")
            # Keep searching with next candidate (retype value).
            continue
        except Exception:
            continue

    try:
        element.press('Enter')
        time.sleep(0.1)
        try:
            final_value = element.input_value()
        except Exception:
            try:
                final_value = element.evaluate("el => el.value")
            except Exception:
                final_value = ""
        if _location_value_matches(context, final_value):
            print(f"[Location] ✓ Confirmed value via Enter fallback: '{final_value}'")
            return True
        # Last resort: force fill with preferred string if available.
        desired_strings = _desired_location_strings(context)
        if desired_strings:
            preferred = desired_strings[0]
            try:
                element.fill(preferred)
                time.sleep(0.1)
                element.press('Enter')
                time.sleep(0.1)
                final_value = element.input_value()
                if _location_value_matches(context, final_value):
                    print(f"[Location] ✓ Forced value to '{final_value}'")
                    return True
            except Exception:
                pass
        print(f"[Location] ⚠️ Fallback Enter produced mismatched value '{final_value}'")
        return False
    except Exception:
        return False


def _fill_easy_apply_dialog(page, dlg, profile: Dict[str, Any], answers: Dict[str, Any]) -> Dict[str, Any]:
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
    summary = {"filled": 0, "required": 0, "missing": [], "skipped_prefilled": 0}
    
    # Track which radio groups have been filled (by name attribute)
    filled_radio_groups = set()

    def norm_key(s: str) -> str:
        import re as _re
        return _re.sub(r"[^a-z0-9]+", "", (s or "").lower())

    def id_locator(dlg_local, fid: str):
        sel = _sel_for_id(fid)
        return dlg_local.locator(sel).first if sel else None
    
    def is_field_prefilled(element, category: str) -> tuple[bool, Optional[str]]:
        """Check if a field already has a value. Returns (is_filled, current_value)"""
        try:
            if category in ["text_input", "text_area"]:
                current_value = element.input_value(timeout=500)
                if current_value and current_value.strip():
                    return True, current_value.strip()
            elif category == "dropdown":
                # Check if a non-placeholder option is selected
                try:
                    current_value = element.input_value(timeout=500)
                    if current_value and current_value.strip():
                        # Filter out common placeholder values - these indicate the field is NOT filled
                        placeholder_values = [
                            "select an option",
                            "please select",
                            "choose an option",
                            "select",
                            "choose",
                            "--",
                            "---",
                        ]
                        value_lower = current_value.strip().lower()
                        if value_lower not in placeholder_values:
                            return True, current_value.strip()
                except Exception:
                    pass
            elif category == "radio":
                # Radio groups are prefilled if any option is checked
                if element.is_checked(timeout=500):
                    return True, "checked"
            elif category == "checkbox":
                if element.is_checked(timeout=500):
                    return True, "checked"
        except Exception:
            pass
        return False, None

    answers_dict: Dict[str, Any] = answers
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
                field_id_value = field.get("id") or fid
                location_field = _looks_like_location_field(label, field_id_value, field.get("type") or "")

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
                print(f"[Fill] Field '{label or field_id_value}' ({category}), required={required}")

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

                if provided is None:
                    print(f"[Fill] No provided answer found for '{label or field_id_value}'")
                else:
                    print(f"[Fill] Using answer '{provided}' for '{label or field_id_value}'")

                # Check if field is already filled (LinkedIn pre-fills from profile)
                is_prefilled, current_value = is_field_prefilled(el, category)
                if is_prefilled:
                    # If we have a provided answer, compare it with current value
                    if provided is not None:
                        # Check if our answer differs from pre-filled value
                        provided_str = str(provided).strip().lower()
                        current_str = str(current_value).strip().lower() if current_value else ""
                        
                        if provided_str == current_str:
                            print(f"[Fill] ✓ Field '{label or field_id_value}' already has matching value: '{current_value}' - SKIPPING")
                            summary["skipped_prefilled"] += 1
                            summary["filled"] += 1  # Count as filled since it has the correct value
                            continue
                        else:
                            print(f"[Fill] ⚠️  Field '{label or field_id_value}' has pre-filled value: '{current_value}' but LLM provided: '{provided}' - OVERWRITING")
                            # Clear the field first, then fill with LLM answer
                            try:
                                el.fill("", timeout=1000)
                                time.sleep(0.1)
                            except Exception:
                                pass
                            # Don't skip - let it fall through to fill with LLM answer
                    else:
                        # No LLM answer provided, accept pre-filled value
                        print(f"[Fill] ✓ Field '{label or field_id_value}' already has value: '{current_value}' (no LLM override)")
                        summary["skipped_prefilled"] += 1
                        summary["filled"] += 1  # Count as filled since it has a value
                        continue

                # Apply provided answers first
                if provided is not None:
                    try:
                        if category == "text_input":
                            if location_field and _fill_location_typeahead(page, dlg, el, str(provided), profile):
                                summary["filled"] += 1
                                continue
                            el.fill(str(provided))
                            summary["filled"] += 1
                            continue
                        if category == "text_area":
                            el.fill(str(provided))
                            summary["filled"] += 1
                            continue
                        if category == "dropdown":
                            print(f"[Dropdown] Target value '{provided}' for field '{label or field_id_value}'")
                            # LinkedIn uses CUSTOM dropdowns (div/button combos), not native <select>
                            # Strategy 1: Try native select first (legacy forms)
                            try:
                                el.select_option(label=str(provided))
                                summary["filled"] += 1
                                print(f"[Dropdown] ✓ Selected '{provided}' using native select (label)")
                                continue
                            except Exception as e1:
                                try:
                                    options = el.locator('option')
                                    option_texts = []
                                    for idx in range(min(options.count(), 20)):
                                        try:
                                            option_texts.append((options.nth(idx).inner_text() or '').strip())
                                        except Exception:
                                            continue
                                    if option_texts:
                                        print(f"[Dropdown] Native option texts: {option_texts}")
                                except Exception:
                                    pass
                                try:
                                    el.select_option(value=str(provided))
                                    summary["filled"] += 1
                                    print(f"[Dropdown] ✓ Selected '{provided}' using native select (value)")
                                    continue
                                except Exception as e2:
                                    # Native select failed - likely a custom dropdown
                                    print(f"[Dropdown] Native select failed: {e1}, {e2}")
                                    print(f"[Dropdown] Trying custom dropdown for: {label}")
                            
                            # Strategy 2: Handle CUSTOM dropdown (click to open, then click option)
                            try:
                                # Scroll element into view WITHOUT scrolling behavior (prevents infinite scroll)
                                el.scroll_into_view_if_needed(timeout=1000)
                                time.sleep(0.2)
                                
                                # Click the dropdown to open options (no force, natural click)
                                el.click(timeout=2000, force=False)
                                time.sleep(0.4)
                                
                                # Find and click the matching option
                                # Try exact text match first, then partial
                                option_clicked = False
                                
                                # Strategy 2a: Look for option in the opened dropdown
                                option_selectors = [
                                    f'select option:has-text("{provided}")',
                                    f'[role="option"]:has-text("{provided}")',
                                    f'[role="listbox"] li:has-text("{provided}")',
                                    f'li[role="option"]:has-text("{provided}")'
                                ]

                                total_candidates = 0
                                for opt_sel in option_selectors:
                                    try:
                                        total_candidates += page.locator(opt_sel).count()
                                    except Exception:
                                        continue
                                print(f"[Dropdown] Candidate options found across selectors: {total_candidates}")
                                
                                for opt_sel in option_selectors:
                                    try:
                                        # Use page.locator to search entire page (dropdown might be in overlay)
                                        option = page.locator(opt_sel).first
                                        if option.count() > 0:
                                            # Ensure visible before clicking
                                            if option.is_visible(timeout=1000):
                                                try:
                                                    option_text = (option.inner_text() or '').strip()
                                                    print(f"[Dropdown] Considering option '{option_text}' via selector '{opt_sel}'")
                                                except Exception:
                                                    option_text = ""
                                                option.click(timeout=2000, force=False)
                                                print(f"[Dropdown] ✓ Selected custom dropdown option: '{provided}'")
                                                option_clicked = True
                                                time.sleep(0.2)
                                                break
                                    except Exception as e_opt:
                                        print(f"[Dropdown] Option selector '{opt_sel}' failed: {e_opt}")
                                        continue
                                
                                if option_clicked:
                                    summary["filled"] += 1
                                    continue
                                else:
                                    print(f"[Dropdown] ⚠️ Could not find visible option '{provided}' in custom dropdown")
                                    # Close dropdown by pressing Escape
                                    try:
                                        page.keyboard.press("Escape")
                                    except Exception:
                                        pass
                                    
                            except Exception as e3:
                                print(f"[Dropdown] Custom dropdown click failed: {e3}")
                                # Try to close any open dropdown
                                try:
                                    page.keyboard.press("Escape")
                                except Exception:
                                    pass
                            
                            # Strategy 3: Last resort - pick first non-placeholder if required
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
                                                print(f"[Dropdown] ⚠️ Fallback: selected first option '{text}'")
                                                summary["filled"] += 1
                                                break
                                except Exception as e4:
                                    print(f"[Dropdown] Fallback failed: {e4}")
                            continue
                        if category == "radio":
                            # Radio buttons: MUST match by name attribute (radio group) + label
                            # LinkedIn forms have multiple Yes/No groups - can't just match by label!
                            target = str(provided).lower()
                            field_name = field.get("name") or ""
                            field_id = field.get("id") or ""
                            
                            # Extract radio group identifier from field_id
                            # LinkedIn format: "urn:li:fsd_formElement:...(...,23106476146,multipleChoice)-0"
                            # Group ID is everything before the last "-0", "-1", "-2" suffix
                            radio_group_id = field_name  # Try name first
                            if not radio_group_id and field_id:
                                # Remove the "-0", "-1", "-2" suffix to get group ID
                                import re
                                match = re.match(r'(.+)-\d+$', field_id)
                                if match:
                                    radio_group_id = match.group(1)
                                else:
                                    radio_group_id = field_id
                            
                            # Skip if this radio group was already filled
                            if radio_group_id and radio_group_id in filled_radio_groups:
                                print(f"[Radio] Skipping '{label}' - group already filled")
                                continue
                            
                            print(f"[Radio] Looking for '{provided}' in group='{radio_group_id}'")
                            
                            radios = dlg.locator('input[type="radio"]').all()
                            clicked = False
                            
                            # Strategy 1: Match by name attribute (radio group) + label text
                            for r in radios:
                                try:
                                    rid = r.get_attribute('id') or ''
                                    rname = r.get_attribute('name') or ''
                                    rlab = ''
                                    
                                    # Get label for this radio
                                    label_element = None
                                    if rid:
                                        label_element = dlg.locator(f'label[for="{rid}"]').first
                                        if label_element.count() > 0:
                                            rlab = (label_element.inner_text() or '').strip()
                                    
                                    # Match criteria: 
                                    # 1. Label matches the target answer
                                    # 2. Radio belongs to the correct group (by name or id)
                                    label_matches = target in rlab.lower()
                                    group_matches = (
                                        (field_name and rname == field_name) or  # Match by group name
                                        (field_id and rid == field_id)  # Match by field id
                                    )
                                    
                                    if label_matches and group_matches:
                                        # Click the LABEL instead of the radio input to avoid interception
                                        if label_element and label_element.count() > 0:
                                            label_element.click(timeout=5000)
                                            print(f"[Radio] ✓ Checked '{rlab}' via label click")
                                        else:
                                            # Fallback: force click the radio input
                                            r.check(force=True)
                                            print(f"[Radio] ✓ Checked '{rlab}' via force check")
                                        
                                        clicked = True
                                        # Mark this group as filled using the extracted group ID
                                        if radio_group_id:
                                            filled_radio_groups.add(radio_group_id)
                                        break
                                except Exception as e:
                                    print(f"[Radio] Error checking radio: {e}")
                                    continue
                            
                            if not clicked:
                                print(f"[Radio] ⚠️ Could not find '{provided}' in correct radio group")
                            
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
                            # Skip file uploads - LinkedIn already has resume from profile
                            # Uploading during apply can cause validation errors
                            print(f"[Fill] Skipping file upload field: {label}")
                            continue
                            # Old code that caused issues:
                            # path = str(provided)
                            # try:
                            #     el.set_input_files(path)
                            #     summary["filled"] += 1
                            #     continue
                            # except Exception:
                            #     pass
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
                    if location_field:
                        location_candidates: List[str] = []
                        if profile.get("location"):
                            location_candidates.append(profile.get("location"))
                        city = profile.get("address_city")
                        state = profile.get("address_state")
                        country = profile.get("address_country")
                        if city and state:
                            location_candidates.append(f"{city}, {state}")
                        if city and country and not state:
                            location_candidates.append(f"{city}, {country}")
                        if city:
                            location_candidates.append(city)
                        if state:
                            location_candidates.append(state)
                        filled_location = False
                        seen_candidates: Set[str] = set()
                        for candidate in location_candidates:
                            candidate_clean = (candidate or "").strip()
                            if not candidate_clean:
                                continue
                            key = candidate_clean.lower()
                            if key in seen_candidates:
                                continue
                            seen_candidates.add(key)
                            if _fill_location_typeahead(page, dlg, el, candidate_clean, profile):
                                summary["filled"] += 1
                                filled_location = True
                                break
                        if filled_location:
                            continue
                    if any(k in lower for k in ["phone"]) and profile.get("phone"):
                        try:
                            el.fill(str(profile["phone"]))
                            summary["filled"] += 1
                        except Exception:
                            pass

                elif category == "checkbox":
                    try:
                        # Only uncheck if it's the "Follow company" checkbox
                        # Check label to avoid unchecking important checkboxes
                        label_lower = (label or "").lower()
                        if "follow" in label_lower:
                            if el.is_checked():
                                el.uncheck()
                                print(f"[Fill] Unchecked 'Follow' checkbox")
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
    
def _detect_step_info(dlg) -> Dict[str, Any]:
    """Detect current step and total steps from the Easy Apply modal.

    Strategies (in priority order):
    1. Progress region with aria-label percentage (most reliable)
    2. Progressbar element with aria-valuenow/aria-valuemax
    3. Parse visible text like "Step X of Y" or "X of Y"
    4. Inspect stepper elements with aria-current="step" and count siblings
    
    Returns a dict: {"current": Optional[int], "total": Optional[int], "progress": Optional[int]}
    """
    import re
    info: Dict[str, Optional[int]] = {"current": None, "total": None, "progress": None, "percent": None}
    try:
        # PRIORITY 1: Use aria-label on region (most reliable for LinkedIn)
        try:
            region = dlg.locator('[role="region"]').first
            if region.count() > 0:
                aria_label = region.get_attribute('aria-label') or ''
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
                    elif progress == 100:
                        info["current"] = info.get("total", 5)
                        if info["total"] is None:
                            info["total"] = 5
                    
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

def navigate_and_fill_easy_apply_form(
    page,
    dlg,
    profile: Dict[str, Any],
    answers: Dict[str, Any],
    max_steps: int = 10,
    submit: bool = False
) -> Dict[str, Any]:
    """
    Navigate through multi-step Easy Apply form, filling each step.
    
    Uses dynamic step detection based on progress bar percentage.
    
    Args:
        page: Playwright page object
        dlg: Dialog locator
        profile: User profile dict
        answers: AI-generated answers dict
        max_steps: Maximum number of steps to traverse (safety limit)
        submit: Whether to click Submit button at the end
    
    Returns:
        Dict with summary: {
            "filled": int,
            "required": int,
            "missing": list,
            "steps_completed": int,
            "submitted": bool,
            "detected_total_steps": int or None
        }
    """
    summary = {
        "filled": 0,
        "required": 0,
        "missing": [],
        "steps_completed": 0,
        "submitted": False,
        "detected_total_steps": None
    }
    
    try:
        import time
        
        # Detect total steps from initial progress
        step_info = _detect_step_info(dlg)
        if step_info.get("total"):
            summary["detected_total_steps"] = step_info["total"]
            print(f"[Navigation] Detected {step_info['total']} total steps")
        
        for step_index in range(max_steps):
            print(f"[Navigation] Processing step {step_index + 1}...")
            
            # Check current progress (support both historic 'percent' and newer 'progress')
            step_info = _detect_step_info(dlg)
            current_percent = step_info.get("progress") or step_info.get("percent")
            if current_percent is not None:
                print(f"[Navigation] Progress: {current_percent}%")
            
            # Fill current step
            step_summary = _fill_easy_apply_dialog(page, dlg, profile, answers)
            summary["filled"] += step_summary.get("filled", 0)
            summary["required"] += step_summary.get("required", 0)
            summary["missing"].extend(step_summary.get("missing", []))
            summary["steps_completed"] = step_index + 1
            
            time.sleep(0.5)
            
            # Check if we're at 100% (review/final step)
            is_final = False
            try:
                if current_percent is not None and int(current_percent) >= 100:
                    is_final = True
                elif isinstance(step_info.get("current"), int) and isinstance(step_info.get("total"), int) and step_info.get("current") == step_info.get("total"):
                    is_final = True
            except Exception:
                is_final = False

            if is_final:
                print(f"[Navigation] Reached final step (100% progress)")
                
                # Look for Submit button
                submit_selectors = [
                    'button:has-text("Submit application")',
                    'button[aria-label*="Submit application"]',
                    'button:has-text("Submit")'
                ]
                
                submit_btn = None
                for sel in submit_selectors:
                    try:
                        btn = dlg.locator(sel).first
                        if btn.count() > 0 and btn.is_visible() and btn.is_enabled():
                            submit_btn = btn
                            print(f"[Navigation] Found Submit button via: {sel}")
                            break
                    except Exception:
                        continue
                
                if submit_btn and submit:
                    try:
                        submit_btn.click()
                        summary["submitted"] = True
                        print(f"[Navigation] ✅ Clicked Submit button")
                        time.sleep(2)
                    except Exception as e:
                        print(f"[Navigation] Error clicking Submit: {e}")
                
                return summary
            
            # Get form config to check navigation buttons
            cfg = _build_form_config_from_dialog(dlg)
            nav = cfg.get("navigation", {})
            
            # Look for Next/Continue or Review button
            next_btn = None
            review_btn = None
            
            # Try Next/Continue button
            next_selectors = [
                'button:has-text("Continue to next step")',
                'button:has-text("Next")',
                'button:has-text("Continue")',
                'button[aria-label*="Continue"]',
                'button[aria-label*="Next"]'
            ]
            
            for sel in next_selectors:
                try:
                    btn = dlg.locator(sel).first
                    if btn.count() > 0 and btn.is_visible() and btn.is_enabled():
                        next_btn = btn
                        break
                except Exception:
                    continue
            
            # Try Review button
            review_selectors = [
                'button:has-text("Review your application")',
                'button:has-text("Review")',
                'button[aria-label*="Review"]'
            ]
            
            for sel in review_selectors:
                try:
                    btn = dlg.locator(sel).first
                    if btn.count() > 0 and btn.is_visible() and btn.is_enabled():
                        review_btn = btn
                        break
                except Exception:
                    continue
            
            # Click Next or Review
            clicked = False
            try:
                if next_btn:
                    next_btn.click(timeout=8000)
                    print(f"[Navigation] Clicked Next/Continue button")
                    clicked = True
                elif review_btn:
                    review_btn.click(timeout=8000)
                    print(f"[Navigation] Clicked Review button")
                    clicked = True
            except Exception as e:
                print(f"[Navigation] Could not click Next/Review: {e}")
                break
            
            if not clicked:
                print(f"[Navigation] No Next/Review button found, assuming final step")
                break
            
            # Wait for next step to load
            time.sleep(1)
        
        return summary
        
    except Exception as e:
        print(f"[Navigation] Error in navigate_and_fill_easy_apply_form: {e}")
        return summary

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
            "steps_estimate": 1,
            "steps_detected_total": None,
            "steps_detected_current": None
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
        # OPTIMIZED: reduced from 300 to 100 form elements to analyze faster
        for i in range(min(n, 100)):
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
                    # OPTIMIZED: reduced from 100 to 30 options to analyze per dropdown
                    for j in range(min(opts.count(), 30)):
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
                    # OPTIMIZED: reduced from 20 to 10 radio options to analyze
                    for j in range(min(radios.count(), 10)):
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

        # Detect true step info if available
        try:
            step_info = _detect_step_info(dlg)
            if isinstance(step_info, dict):
                form_config["meta"]["steps_detected_current"] = step_info.get("current")
                form_config["meta"]["steps_detected_total"] = step_info.get("total")
        except Exception:
            pass
    except Exception:
        pass

    return form_config
