"""
Screenshot and Visual Logging Utilities for Robocorp Log

This module provides enhanced visual logging capabilities:
- Automatic browser screenshots embedded in log.html
- Base64 image encoding for HTML embedding
- Console message formatting with emoji and colors
- Screenshot annotations and context

Integrates with robocorp-browser and robocorp-log for comprehensive visual debugging.
"""

import base64
from io import BytesIO
from pathlib import Path
from typing import Optional, Union, Literal
from datetime import datetime

try:
    from robocorp import log
    from robocorp.browser import page as get_page
    ROBOCORP_AVAILABLE = True
except ImportError:
    ROBOCORP_AVAILABLE = False

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


try:
    # Import helper that knows the configured output_log_level
    from .robolog import should_print_to_console
except Exception:
    # Fallback: preserve previous behavior by indicating that robocorp.log
    # will NOT print the messages (so console_message will still be used).
    def should_print_to_console(level: str) -> bool:  # type: ignore[no-redef]
        return False


def capture_screenshot(
    name: str = "screenshot",
    message: Optional[str] = None,
    level: Literal["INFO", "WARN", "ERROR"] = "INFO",
    full_page: bool = False,
    annotate: Optional[str] = None,
    save_to_disk: bool = True,
    output_dir: Optional[str] = None
) -> Optional[str]:
    """
    Capture browser screenshot and embed it in the log.html.
    
    Args:
        name: Name for the screenshot (used in filename)
        message: Optional message to display with screenshot
        level: Log level (INFO, WARN, or ERROR)
        full_page: Whether to capture full page or just viewport
        annotate: Optional text to overlay on the screenshot
        save_to_disk: Whether to also save screenshot to disk
        output_dir: Directory to save screenshot file (default: ./output/screenshots)
    
    Returns:
        Path to saved screenshot file, or None if failed
    
    Example:
        >>> capture_screenshot("login_page", "User logged in successfully")
        >>> capture_screenshot("error_state", "Failed to find element", level="ERROR")
    """
    if not ROBOCORP_AVAILABLE:
        print(f"[Screenshot] Robocorp not available, skipping screenshot: {name}")
        return None
    
    try:
        page = get_page()
        
        # Capture screenshot as bytes
        screenshot_bytes = page.screenshot(full_page=full_page)
        
        # Optionally annotate the screenshot
        if annotate and PIL_AVAILABLE:
            screenshot_bytes = _annotate_image(screenshot_bytes, annotate)
        
        # Convert to base64 for HTML embedding
        base64_image = base64.b64encode(screenshot_bytes).decode('utf-8')
        
        # Build HTML with optional message
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        html_content = f"""
        <div style="border: 2px solid #{'#d32f2f' if level == 'ERROR' else '#1976d2' if level == 'INFO' else '#f57c00'}; 
                    border-radius: 8px; 
                    padding: 16px; 
                    margin: 16px 0; 
                    background: #{'#ffebee' if level == 'ERROR' else '#e3f2fd' if level == 'INFO' else '#fff3e0'};">
            <div style="font-weight: bold; margin-bottom: 8px; color: #{'#d32f2f' if level == 'ERROR' else '#1976d2' if level == 'INFO' else '#f57c00'};">
                📸 {name} ({timestamp})
            </div>
            {f'<div style="margin-bottom: 8px;">{message}</div>' if message else ''}
            <img src="data:image/png;base64,{base64_image}" 
                 style="max-width: 100%; border: 1px solid #ddd; border-radius: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);" 
                 alt="{name}"/>
        </div>
        """
        
        # Embed in log.html
        log.html(html_content, level=level)

        # Also log a concise console message only if robocorp.log won't already
        # print the message at this level (avoids duplicate console output)
        emoji = "📸" if level == "INFO" else "⚠️" if level == "WARN" else "❌"
        try:
            mapped_level = {'INFO': 'info', 'WARN': 'warn', 'ERROR': 'critical'}.get(level, 'info')
            if not should_print_to_console(mapped_level):
                log.console_message(
                    f"{emoji} Screenshot captured: {name}{f' - {message}' if message else ''}",
                    kind="important" if level == "INFO" else "error" if level == "ERROR" else "regular"
                )
        except Exception:
            # Fall back to printing when something unexpected happens
            log.console_message(
                f"{emoji} Screenshot captured: {name}{f' - {message}' if message else ''}",
                kind="important" if level == "INFO" else "error" if level == "ERROR" else "regular"
            )
        
        # Optionally save to disk
        if save_to_disk:
            if output_dir is None:
                output_dir = "./output/screenshots"
            
            screenshot_path = Path(output_dir)
            screenshot_path.mkdir(parents=True, exist_ok=True)
            
            filename = f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            filepath = screenshot_path / filename
            
            with open(filepath, 'wb') as f:
                f.write(screenshot_bytes)
            
            log.info(f"[Screenshot] Saved to: {filepath}")
            return str(filepath)
        
        return None
        
    except Exception as e:
        log.warn(f"[Screenshot] Failed to capture {name}: {e}")
        return None


def _annotate_image(image_bytes: bytes, text: str) -> bytes:
    """
    Add text annotation overlay to an image.
    
    Args:
        image_bytes: Original image as bytes
        text: Text to overlay on the image
    
    Returns:
        Annotated image as bytes
    """
    if not PIL_AVAILABLE:
        return image_bytes
    
    try:
        # Open image from bytes
        image = Image.open(BytesIO(image_bytes))
        draw = ImageDraw.Draw(image)
        
        # Use default font (try to load a better one if available)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        except:
            font = ImageFont.load_default()
        
        # Calculate text position (top-left with padding)
        padding = 10
        
        # Draw background rectangle for text
        bbox = draw.textbbox((padding, padding), text, font=font)
        draw.rectangle(
            [(bbox[0] - 5, bbox[1] - 5), (bbox[2] + 5, bbox[3] + 5)],
            fill=(0, 0, 0, 180)
        )
        
        # Draw text
        draw.text((padding, padding), text, fill=(255, 255, 255), font=font)
        
        # Convert back to bytes
        output = BytesIO()
        image.save(output, format='PNG')
        return output.getvalue()
        
    except Exception as e:
        log.warn(f"[Screenshot] Failed to annotate image: {e}")
        return image_bytes


def log_success(message: str, details: Optional[str] = None, screenshot: bool = False, screenshot_name: Optional[str] = None):
    """
    Log a success message with emoji and optional screenshot.
    
    Args:
        message: Success message
        details: Optional additional details
        screenshot: Whether to capture a screenshot
        screenshot_name: Name for the screenshot
    
    Example:
        >>> log_success("Login successful", details="User: john@example.com")
        >>> log_success("Job applied", screenshot=True, screenshot_name="application_complete")
    """
    log.info("✅", message)
    try:
        if not should_print_to_console("info"):
            log.console_message(f"✅ {message}", kind="important")
    except Exception:
        log.console_message(f"✅ {message}", kind="important")

    if details:
        log.info(f"   ℹ️  {details}")
    
    if screenshot and ROBOCORP_AVAILABLE:
        capture_screenshot(
            name=screenshot_name or "success",
            message=message,
            level="INFO"
        )


def log_warning(message: str, details: Optional[str] = None, screenshot: bool = False, screenshot_name: Optional[str] = None):
    """
    Log a warning message with emoji and optional screenshot.
    
    Args:
        message: Warning message
        details: Optional additional details
        screenshot: Whether to capture a screenshot
        screenshot_name: Name for the screenshot
    
    Example:
        >>> log_warning("Retry attempt 2 of 3", details="Network timeout")
        >>> log_warning("Element not found", screenshot=True, screenshot_name="missing_element")
    """
    log.warn("⚠️", message)
    try:
        if not should_print_to_console("warn"):
            log.console_message(f"⚠️  {message}", kind="error")
    except Exception:
        log.console_message(f"⚠️  {message}", kind="error")

    if details:
        log.warn(f"   ℹ️  {details}")
    
    if screenshot and ROBOCORP_AVAILABLE:
        capture_screenshot(
            name=screenshot_name or "warning",
            message=message,
            level="WARN"
        )


def log_error(message: str, details: Optional[str] = None, screenshot: bool = True, screenshot_name: Optional[str] = None):
    """
    Log an error message with emoji and automatic screenshot.
    
    Args:
        message: Error message
        details: Optional additional details
        screenshot: Whether to capture a screenshot (default: True)
        screenshot_name: Name for the screenshot
    
    Example:
        >>> log_error("Failed to submit form", details="Submit button not clickable")
        >>> log_error("Database connection failed", screenshot=False)
    """
    log.critical("❌", message)
    try:
        if not should_print_to_console("critical"):
            log.console_message(f"❌ {message}", kind="error")
    except Exception:
        log.console_message(f"❌ {message}", kind="error")

    if details:
        log.critical(f"   ℹ️  {details}")
    
    if screenshot and ROBOCORP_AVAILABLE:
        capture_screenshot(
            name=screenshot_name or "error",
            message=message,
            level="ERROR"
        )


def log_step(step_number: int, total_steps: int, message: str, screenshot: bool = False):
    """
    Log a step in a multi-step process with progress indicator.
    
    Args:
        step_number: Current step number (1-indexed)
        total_steps: Total number of steps
        message: Step description
        screenshot: Whether to capture a screenshot
    
    Example:
        >>> log_step(1, 5, "Opening LinkedIn")
        >>> log_step(2, 5, "Searching for jobs", screenshot=True)
    """
    progress = "█" * step_number + "░" * (total_steps - step_number)
    percentage = int((step_number / total_steps) * 100)
    
    log.info(f"[Step {step_number}/{total_steps}]", message)
    try:
        if not should_print_to_console("info"):
            log.console_message(
                f"[{step_number}/{total_steps}] {progress} {percentage}% - {message}",
                kind="task_name"
            )
    except Exception:
        log.console_message(
            f"[{step_number}/{total_steps}] {progress} {percentage}% - {message}",
            kind="task_name"
        )
    
    if screenshot and ROBOCORP_AVAILABLE:
        capture_screenshot(
            name=f"step_{step_number}_{message.replace(' ', '_')[:30]}",
            message=f"Step {step_number}/{total_steps}: {message}",
            level="INFO"
        )


def log_metric(name: str, value: Union[int, float, str], unit: Optional[str] = None, emoji: str = "📊"):
    """
    Log a metric with visual formatting.
    
    Args:
        name: Metric name
        value: Metric value
        unit: Optional unit (e.g., "ms", "jobs", "%")
        emoji: Emoji to use (default: 📊)
    
    Example:
        >>> log_metric("Jobs Found", 42, "jobs", "🔍")
        >>> log_metric("Processing Time", 1.23, "seconds", "⏱️")
        >>> log_metric("Success Rate", 95, "%", "✅")
    """
    unit_str = f" {unit}" if unit else ""
    log.info(f"{emoji} {name}:", value, unit_str)
    try:
        if not should_print_to_console("info"):
            log.console_message(f"{emoji} {name}: {value}{unit_str}", kind="important")
    except Exception:
        log.console_message(f"{emoji} {name}: {value}{unit_str}", kind="important")


def embed_html_table(title: str, data: list[dict], level: Literal["INFO", "WARN", "ERROR"] = "INFO"):
    """
    Embed a formatted HTML table in the log.
    
    Args:
        title: Table title
        data: List of dictionaries (each dict is a row)
        level: Log level
    
    Example:
        >>> jobs = [
        ...     {"title": "Software Engineer", "company": "Acme", "location": "Remote"},
        ...     {"title": "Data Scientist", "company": "TechCo", "location": "NYC"}
        ... ]
        >>> embed_html_table("Jobs Found", jobs)
    """
    if not data:
        log.info(f"[Table] {title}: No data")
        return
    
    # Get headers from first row
    headers = list(data[0].keys())
    
    # Build HTML table
    html = f"""
    <div style="margin: 16px 0; border: 1px solid #ddd; border-radius: 8px; overflow: hidden;">
        <div style="background: #{'#d32f2f' if level == 'ERROR' else '#1976d2' if level == 'INFO' else '#f57c00'}; 
                    color: white; padding: 12px; font-weight: bold;">
            {title}
        </div>
        <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
            <thead>
                <tr style="background: #f5f5f5;">
                    {''.join(f'<th style="padding: 8px; text-align: left; border-bottom: 2px solid #ddd;">{h}</th>' for h in headers)}
                </tr>
            </thead>
            <tbody>
                {''.join(
                    f"<tr style='border-bottom: 1px solid #eee;'>" +
                    ''.join(f'<td style="padding: 8px;">{row.get(h, "")}</td>' for h in headers) +
                    "</tr>"
                    for row in data
                )}
            </tbody>
        </table>
    </div>
    """
    
    log.html(html, level=level)
    log.info(f"[Table] {title}: {len(data)} rows")


def log_section_start(section_name: str, emoji: str = "📌"):
    """
    Mark the start of a major section in the logs.
    
    Args:
        section_name: Name of the section
        emoji: Emoji to use
    
    Example:
        >>> log_section_start("Job Search Phase", "🔍")
        >>> # ... do work ...
        >>> log_section_end("Job Search Phase")
    """
    separator = "=" * 80
    # Structured logs for HTML and .robolog
    log.info("=" * 80)
    log.info(f"{emoji} {section_name}")
    log.info("=" * 80)

    # Only emit the decorative console output when robocorp.log won't
    # already print the info-level messages to stdout (prevents duplicates)
    try:
        if not should_print_to_console("info"):
            log.console_message(f"\n{separator}", kind="regular")
            log.console_message(f"{emoji} {section_name}", kind="task_name")
            log.console_message(separator, kind="regular")
    except Exception:
        log.console_message(f"\n{separator}", kind="regular")
        log.console_message(f"{emoji} {section_name}", kind="task_name")
        log.console_message(separator, kind="regular")


def log_section_end(section_name: str, emoji: str = "✅"):
    """
    Mark the end of a major section in the logs.
    
    Args:
        section_name: Name of the section
        emoji: Emoji to use
    
    Example:
        >>> log_section_end("Job Search Phase", "✅")
    """
    separator = "=" * 80
    # Structured logs for HTML and .robolog
    log.info("=" * 80)
    log.info(f"{emoji} {section_name} - Complete")
    log.info("=" * 80)

    try:
        if not should_print_to_console("info"):
            log.console_message(separator, kind="regular")
            log.console_message(f"{emoji} {section_name} - Complete", kind="important")
            log.console_message(f"{separator}\n", kind="regular")
    except Exception:
        log.console_message(separator, kind="regular")
        log.console_message(f"{emoji} {section_name} - Complete", kind="important")
        log.console_message(f"{separator}\n", kind="regular")


def log_json_data(title: str, data: dict, level: Literal["INFO", "WARN", "ERROR"] = "INFO"):
    """
    Log JSON/dict data with pretty formatting in HTML.
    
    Args:
        title: Title for the data
        data: Dictionary to log
        level: Log level
    
    Example:
        >>> log_json_data("API Response", {"status": "success", "count": 42})
    """
    import json
    
    json_str = json.dumps(data, indent=2)
    html = f"""
    <div style="margin: 16px 0; border: 1px solid #ddd; border-radius: 8px; overflow: hidden;">
        <div style="background: #{'#d32f2f' if level == 'ERROR' else '#1976d2' if level == 'INFO' else '#f57c00'}; 
                    color: white; padding: 12px; font-weight: bold;">
            {title}
        </div>
        <pre style="margin: 0; padding: 16px; background: #f5f5f5; overflow-x: auto; font-family: monospace; font-size: 13px;">{json_str}</pre>
    </div>
    """
    
    log.html(html, level=level)
    log.info(f"[JSON] {title}")


# Export all functions
__all__ = [
    'capture_screenshot',
    'log_success',
    'log_warning',
    'log_error',
    'log_step',
    'log_metric',
    'embed_html_table',
    'log_section_start',
    'log_section_end',
    'log_json_data',
]
