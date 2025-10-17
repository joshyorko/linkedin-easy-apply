from sema4ai.actions import ActionError, Response, action
from robocorp import browser
import dotenv
import os
import time
import re
from datetime import datetime

from ..utils.tools import configure_browser
from ..utils.robolog import setup_logging, log, cleanup_logging, hide_sensitive_value
from ..utils.robolog_screenshots import (
    log_section_start, log_section_end,
    log_success, log_warning, log_error,
    capture_screenshot
)

dotenv.load_dotenv()

# Global LinkedIn credentials from environment variables
LINKEDIN_USERNAME = os.getenv("LINKEDIN_USERNAME")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD")


@action
def set_browser_context(
    headless_mode: bool = True
) -> Response:
    """Logs into LinkedIn and returns a Response indicating login success.
    
    Args:
        headless_mode: Whether to run the browser in headless mode (default: True).
    
    Returns:
        Response indicating login success.
    """
    # Setup logging
    run_id = f"login_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    setup_logging(
        output_dir=f"./output/{run_id}",
        enable_html_report=True,
        log_level="info"
    )
    
    try:
        log_section_start("LinkedIn Login", "🔐")

        username = os.getenv("LINKEDIN_USERNAME") or LINKEDIN_USERNAME
        password = os.getenv("LINKEDIN_PASSWORD") or LINKEDIN_PASSWORD

        # Hide credentials from logs
        if username:
            hide_sensitive_value(username)
        if password:
            hide_sensitive_value(password)

        missing = []
        if not username:
            missing.append("LINKEDIN_USERNAME")
        if not password:
            missing.append("LINKEDIN_PASSWORD")
        if missing:
            log_error(
                "Missing LinkedIn credentials",
                details=f"Missing: {', '.join(missing)}",
                screenshot=False,
            )
            raise ActionError(
                "Missing LinkedIn credential(s): "
                + ", ".join(missing)
                + ". Set them in your environment or .env file before running set_browser_context."
            )

        log.info(f"Browser mode: {'headless' if headless_mode else 'headed'}")
        configure_browser(headless_mode=headless_mode)
        page = browser.goto("https://www.linkedin.com/login")
        log.info("Navigated to LinkedIn login page")

        def _fill_first(locator, value: str) -> bool:
            try:
                if locator.count() == 0:
                    return False
                locator.first.fill(value)
                return True
            except Exception:
                return False

        username_value = str(username)
        password_value = str(password)

        username_locators = [
            page.get_by_role("textbox", name=re.compile(r"Email|Phone", re.I)),
            page.locator("input[name='session_key']"),
            page.locator("input#session_key"),
            page.locator("input#username"),
        ]
        password_locators = [
            page.get_by_role("textbox", name=re.compile(r"Password", re.I)),
            page.locator("input[name='session_password']"),
            page.locator("input#session_password"),
            page.locator("input#password"),
        ]

        if not any(_fill_first(locator, username_value) for locator in username_locators):
            log_error(
                "Could not locate LinkedIn username/email input",
                details="Tried multiple selectors, none worked",
                screenshot=True,
                screenshot_name="username_field_not_found",
            )
            raise ActionError("Could not locate the LinkedIn username/email input on the login page.")

        if not any(_fill_first(locator, password_value) for locator in password_locators):
            log_error(
                "Could not locate LinkedIn password input",
                details="Tried multiple selectors, none worked",
                screenshot=True,
                screenshot_name="password_field_not_found",
            )
            raise ActionError("Could not locate the LinkedIn password input on the login page.")

        log.info("Credentials filled, submitting login form...")
        page.get_by_role("button", name="Sign in", exact=True).click()

        # Wait and handle post-login flows (verification, Apple sign-in prompts, etc.)
        log.info("Waiting for post-login redirect...")
        time.sleep(3)

        # Check for successful login indicators FIRST
        current_url = page.url.lower()
        success_indicators = [
            "feed" in current_url,
            "mynetwork" in current_url,
            "/feed/" in current_url,
            "/in/" in current_url,
        ]

        if any(success_indicators):
            log_success(
                "LinkedIn login successful",
                details=f"Redirected to: {current_url}",
                screenshot=True,
                screenshot_name="login_success",
            )
            log_section_end("LinkedIn Login", "✅")
            page.close()
            return Response(result={
                "success": True,
                "message": "LinkedIn login successful.",
                "log_file": f"./output/{run_id}/log.html",
            })

        # Check if we landed on verification/additional auth pages
        page_content = ""
        try:
            page_content = page.content().lower()
        except Exception:
            pass

        verification_indicators = [
            "apple" in current_url,
            "verify" in current_url,
            "challenge" in current_url,
            "checkpoint" in current_url,
            "apple account" in page_content,
            "verification" in page_content,
            "security check" in page_content,
        ]

        if any(verification_indicators):
            warning_msg = (
                "LinkedIn login redirected to verification/additional authentication page.\n"
                f"Current URL: {page.url}\n\n"
                "This typically happens when:\n"
                "1. Your LinkedIn account has Apple Sign-In enabled - disable it in LinkedIn settings\n"
                "2. LinkedIn detected automated login and requires verification\n"
                "3. The account needs additional security verification\n\n"
                "Recommended actions:\n"
                "- Run this action in non-headless mode (headless_mode=False) to manually complete verification\n"
                "- After manual verification, the browser context will be saved for future automated runs\n"
                "- Consider disabling Apple Sign-In in your LinkedIn account settings"
            )

            log_warning(
                "Verification required",
                details=warning_msg,
                screenshot=True,
                screenshot_name="verification_required",
            )

            # Keep browser open for manual intervention if not headless
            if not headless_mode:
                log.info("Browser will remain open for 30 seconds for manual verification...")
                time.sleep(30)
            else:
                time.sleep(5)

            log_section_end("LinkedIn Login", "⚠️")
            page.close()
            return Response(result={
                "status": "verification_required",
                "message": warning_msg,
                "current_url": page.url,
                "log_file": f"./output/{run_id}/log.html",
            })

        # Unclear state - return info for debugging
        log_warning(
            "Uncertain login state",
            details=f"Landed on unexpected page: {page.url}",
            screenshot=True,
            screenshot_name="uncertain_state",
        )
        log_section_end("LinkedIn Login", "❓")
        page.close()
        return Response(result={
            "status": "uncertain",
            "message": f"Login completed but landed on unexpected page: {page.url}",
            "recommendation": "Verify login state by checking the current URL or running in non-headless mode.",
            "log_file": f"./output/{run_id}/log.html",
        })
    
    except ActionError as e:
        # ActionError already logged above, just re-raise
        log.exception()
        raise
    
    except Exception as e:
        # Unexpected error with screenshot
        log_error(
            "Login failed with unexpected error",
            details=str(e),
            screenshot=True,
            screenshot_name="unexpected_error"
        )
        log.exception()
        try:
            page.close()
        except Exception:
            pass
        raise ActionError(f"Login failed: {e}")
    
    finally:
        cleanup_logging()
