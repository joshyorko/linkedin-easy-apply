"""Synthetic-only fixture; no application package or account data is loaded."""

from actions import action


@action(is_consequential=False)
def synthetic_echo(message: str) -> str:
    """Echo synthetic text to prove action worker execution.

    Args:
        message: Synthetic test text.

    Returns:
        Echoed text with a stable fixture prefix.
    """
    return f"easy-apply-fixture:{message}"


@action(is_consequential=False)
def synthetic_browser() -> bool:
    """Fill a local inline form with all browser network requests blocked.

    Returns:
        True when synthetic field values match; no form is submitted.
    """
    from robocorp import browser

    browser.configure(headless=True)
    context = browser.context()
    context.route("**/*", lambda route: route.abort())
    page = context.new_page()
    try:
        page.set_content('<label>Name<input id="name"></label>')
        page.get_by_label("Name").fill("Synthetic Example")
        assert page.locator("#name").input_value() == "Synthetic Example"
        assert page.url == "about:blank"
        return True
    finally:
        page.close()
