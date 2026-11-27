"""Verified work arrangement and optional Easy Apply filters."""
import time
from urllib.parse import parse_qs, urlparse
from actions import ActionError
from playwright.sync_api import Error as PlaywrightError
from ..utils.robolog import log
from ..utils.robolog_screenshots import log_warning

def _apply_search_filters(
    page,
    *,
    easy_apply_only: bool,
    remote: bool,
    hybrid: bool,
    onsite: bool,
) -> dict:
    """Apply the requested LinkedIn filters and return the active filter set."""
    from playwright.sync_api import Error as PlaywrightError

    requested_filters = {
        "remote": remote,
        "hybrid": hybrid,
        "onsite": onsite,
        "easy_apply_only": easy_apply_only,
    }
    active_filters = {
        "remote": False,
        "hybrid": False,
        "onsite": False,
        "easy_apply_only": False,
    }
    work_filters_requested = [
        mode
        for mode, requested in (
            ("remote", remote),
            ("hybrid", hybrid),
            ("onsite", onsite),
        )
        if requested
    ]

    if not easy_apply_only and not work_filters_requested:
        return {**requested_filters, "active": active_filters}

    filters_opened = False
    for button_name in ["Show all filters. Clicking", "Show all filters", "All filters"]:
        try:
            page.get_by_role("button", name=button_name).click(timeout=5000)
            filters_opened = True
            print(f"[Filters] Opened filters dialog via '{button_name}'")
            break
        except PlaywrightError:
            continue

    if not filters_opened:
        for selector in [
            'button[aria-label*="Show all filters"]',
            'button:has-text("All filters")',
            'button[aria-label*="filters"]',
        ]:
            try:
                page.locator(selector).first.click(timeout=3000)
                filters_opened = True
                print(f"[Filters] Opened filters dialog via CSS selector: {selector}")
                break
            except PlaywrightError:
                continue

    if not filters_opened:
        if easy_apply_only:
            raise ActionError(
                "Easy Apply filter requested, but LinkedIn's filters dialog could not be opened."
            )
        print("[Filters] Could not open filters dialog; requested work filters were not applied")
        return {**requested_filters, "active": active_filters}

    if easy_apply_only:
        toggled = False
        easy_apply_toggle_selectors = [
            'input[id*="easyApply"]',
            'input[name*="easyApply"]',
            'input[aria-label*="Easy Apply"]',
            'label:has-text("Easy Apply")',
            '[role="switch"][aria-label*="Easy Apply"]',
            'button[role="switch"]:has-text("Easy Apply")',
            'div.search-reusables__filter-binary-toggle:has-text("Easy Apply") input',
            'div.search-reusables__filter-binary-toggle:has-text("Easy Apply") label',
        ]

        for selector in easy_apply_toggle_selectors:
            try:
                elem = page.locator(selector).first
                if elem.count() == 0:
                    continue
                is_checked = elem.get_attribute("aria-checked") == "true"
                if hasattr(elem, "is_checked"):
                    is_checked = is_checked or elem.is_checked()
                if not is_checked:
                    elem.click(timeout=3000)
                toggled = True
                break
            except PlaywrightError:
                continue

        if not toggled:
            for text in [
                "Off Toggle Easy Apply filter",
                "Toggle Easy Apply filter",
                "Easy Apply",
            ]:
                try:
                    elem = page.get_by_text(text, exact=False).first
                    if elem.count() > 0:
                        elem.click(timeout=3000)
                        toggled = True
                        break
                except PlaywrightError:
                    continue

        if not toggled:
            raise ActionError(
                "Easy Apply filter requested, but LinkedIn's Easy Apply control could not be toggled."
            )

    if work_filters_requested:
        try:
            filters_container = page.get_by_label("All filters", exact=True)
        except PlaywrightError:
            try:
                filters_container = page.get_by_role("dialog")
            except PlaywrightError:
                filters_container = page

        arrangement_label_map = {
            "remote": ["Remote Filter", "Remote (work from home)", "Remote"],
            "hybrid": ["Hybrid Filter", "Hybrid"],
            "onsite": ["On-site", "Onsite"],
        }

        def try_click_patterns(container, patterns: list[str]) -> str | None:
            for pattern in patterns:
                try:
                    label_locator = container.locator("label").filter(has_text=pattern)
                    if label_locator.count() > 0:
                        label_locator.first.click(timeout=2000)
                        return pattern
                except PlaywrightError:
                    pass
                try:
                    container.get_by_text(pattern, exact=False).first.click(timeout=2000)
                    return pattern
                except PlaywrightError:
                    pass
            return None

        for mode in work_filters_requested:
            applied_pattern = try_click_patterns(filters_container, arrangement_label_map[mode])
            if applied_pattern:
                print(f"[Filters] Applied work arrangement filter: {mode}")
                continue

            try:
                keyword = {
                    "remote": "remote",
                    "hybrid": "hybrid",
                    "onsite": "on",
                }[mode]
                labels = filters_container.locator("label")
                for index in range(min(labels.count(), 40)):
                    label = labels.nth(index)
                    if keyword in label.inner_text(timeout=1000).lower():
                        label.click()
                        print(f"[Filters] Applied work arrangement filter by scan: {mode}")
                        break
                else:
                    print(f"[Filters] Could not apply work arrangement filter: {mode}")
            except PlaywrightError:
                print(f"[Filters] Could not apply work arrangement filter: {mode}")

    applied = False
    for button_name in [
        "Apply current filters to show",
        "Apply filters",
        "Show results",
        "View results",
    ]:
        try:
            button = page.get_by_role("button", name=button_name).first
            if button.count() > 0:
                button.click(timeout=5000)
                applied = True
                break
        except PlaywrightError:
            continue
    if not applied:
        try:
            page.get_by_label("All filters", exact=True).get_by_role("button").filter(
                has_text="Apply"
            ).first.click()
            applied = True
        except PlaywrightError:
            print("[Filters] Could not find an Apply/Show results button")

    query = parse_qs(urlparse(page.url).query)
    workplace_codes = {
        code
        for value in query.get("f_WT", [])
        for code in value.split(",")
    }
    active_filters.update(
        {
            "remote": "2" in workplace_codes,
            "hybrid": "3" in workplace_codes,
            "onsite": "1" in workplace_codes,
            "easy_apply_only": "true" in query.get("f_AL", []),
        }
    )

    if easy_apply_only and not active_filters["easy_apply_only"]:
        raise ActionError(
            "Easy Apply filter requested, but LinkedIn did not confirm it in the search URL "
            f"({page.url})."
        )
    if easy_apply_only:
        print("[Filters] Easy Apply filter confirmed active")

    return {**requested_filters, "active": active_filters}
