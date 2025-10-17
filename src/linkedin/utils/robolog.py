
"""Robocorp Logging Configuration and Utilities

This module provides centralized logging configuration using Robocorp's robocorp-log
library (v3.0+), which offers:
- Structured logging with visual HTML reports (log.html)
- Automatic method call tracking
- Sensitive data redaction (passwords, API keys, tokens)
- Better error tracking with detailed stack traces
- Compact .robolog format for storage
- Built-in context managers for security

Documentation: https://sema4.ai/docs/automation/python/robocorp/robocorp-log
API Reference: https://sema4.ai/docs/automation/python/robocorp/robocorp-log/api

Minimum Version: robocorp-log >= 3.0.1
"""

import os
from pathlib import Path
from typing import Optional
from datetime import datetime

# Import robocorp.log (required dependency in package.yaml)
from robocorp import log


# Global flag to track if logging has been initialized
_LOGGING_INITIALIZED = False
# Track configured output log level so other modules can decide
# whether to use console_message or rely on robocorp.log's output.
_OUTPUT_LOG_LEVEL: str = "info"


def setup_logging(
    output_dir: Optional[str] = None,
    max_file_size: str = "5MB",
    max_files: int = 10,
    log_level: str = "info",
    output_log_level: str = "info",
    enable_html_report: bool = True
) -> None:
    """
    Initialize Robocorp logging with comprehensive configuration.
    
    This should be called once at the start of your application, preferably
    in the main entry point or first action.
    
    Args:
        output_dir: Directory for log files (default: ./output)
        max_file_size: Max size per log file (e.g., "1MB", "5MB")
        max_files: Max number of log files to keep
        log_level: Minimum level for log.html (debug|info|warn|critical)
        output_log_level: Minimum level for console output
        enable_html_report: Whether to generate log.html report
    
    Example:
        >>> from linkedin.utils.robolog import setup_logging
        >>> setup_logging(output_dir="./logs", log_level="info")
    """
    global _LOGGING_INITIALIZED
    
    if _LOGGING_INITIALIZED:
        log.info("[Robolog] Logging already initialized, skipping setup")
        return
    
    # Determine output directory
    if output_dir is None:
        output_dir = os.getenv("ROBOCORP_LOG_OUTPUT_DIR", "./output")
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Configure log level - use string literals for type safety
    normalized_log_level = log_level.lower()
    normalized_output_level = output_log_level.lower()
    
    # Validate levels
    valid_levels = ["debug", "info", "warn", "critical", "none"]
    if normalized_log_level not in valid_levels:
        normalized_log_level = "info"
    if normalized_output_level not in valid_levels:
        normalized_output_level = "info"
    
    # Setup global log configuration with string literals
    # API: https://sema4.ai/docs/automation/python/robocorp/robocorp-log/api#setup_log
    log.setup_log(
        max_value_repr_size="200k",  # Limit repr size to prevent huge logs
        log_level=normalized_log_level,  # type: ignore[arg-type]
        output_log_level=normalized_output_level,  # type: ignore[arg-type]
        output_stream={
            'debug': 'stdout',
            'info': 'stdout',
            'warn': 'stderr',
            'critical': 'stderr'
        }
    )
    
    # Setup log output with HTML report
    # API: https://sema4.ai/docs/automation/python/robocorp/robocorp-log/api#add_log_output
    log_html_path = output_path / "log.html" if enable_html_report else None
    
    log.add_log_output(
        output_dir=str(output_path),
        max_file_size=max_file_size,
        max_files=max_files,
        log_html=str(log_html_path) if log_html_path else None,
        log_html_style="standalone",  # Options: 'standalone' or 'vscode'
        min_messages_per_file=50
    )
    
    # Configure sensitive data protection
    _configure_sensitive_data_protection()
    # Persist configured output log level for other helpers
    global _OUTPUT_LOG_LEVEL
    _OUTPUT_LOG_LEVEL = normalized_output_level

    _LOGGING_INITIALIZED = True
    
    log.info("=" * 80)
    log.info("[Robolog] LinkedIn Easy Apply Automation")
    log.info(f"[Robolog] Session started: {datetime.now().isoformat()}")
    log.info(f"[Robolog] Log directory: {output_path.absolute()}")
    if log_html_path:
        log.info(f"[Robolog] HTML report: {log_html_path.absolute()}")
    log.info(f"[Robolog] Log level: {log_level}, Console level: {output_log_level}")
    log.info("=" * 80)


def _configure_sensitive_data_protection() -> None:
    """
    Configure automatic redaction of sensitive information.
    
    Robocorp log will automatically redact variables and arguments
    containing these names or patterns.
    """
    # Add sensitive variable names (exact match or substring)
    sensitive_names = [
        "password",
        "passwd",
        "pwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "auth_token",
        "bearer",
        "credential",
        "private_key",
        "session_id",
        "session_token",
        "cookie",
        "csrf",
        "openai_api_key",
        "linkedin_password",
    ]
    
    for name in sensitive_names:
        log.add_sensitive_variable_name(name)
    
    # Configure what should NOT be hidden (prevent over-redaction)
    config = log.hide_strings_config()
    
    # Don't hide common words or short strings
    config.dont_hide_strings_smaller_or_equal_to = 3
    config.dont_hide_strings.add('None')
    config.dont_hide_strings.add('True')
    config.dont_hide_strings.add('False')
    config.dont_hide_strings.add('null')
    config.dont_hide_strings.add('undefined')
    
    log.debug("[Robolog] Sensitive data protection configured")


def hide_sensitive_value(value: str) -> None:
    """
    Explicitly mark a value as sensitive for redaction in logs.
    
    Use this for runtime values that should be hidden (passwords, API keys, etc.)
    
    Args:
        value: The string value to hide from all future log output
    
    Example:
        >>> password = get_password_from_user()
        >>> hide_sensitive_value(password)
    """
    if value:
        log.hide_from_output(value)


def get_output_log_level() -> str:
    """
    Return the currently configured output log level used when setup_logging
    was invoked. This is useful for higher-level helpers that decide whether
    to emit additional console-only messages (via log.console_message) or
    rely on robocorp.log's configured output channel.
    """
    return _OUTPUT_LOG_LEVEL


def should_print_to_console(message_level: str) -> bool:
    """
    Decide whether a message at `message_level` will be printed to the
    console by robocorp.log based on the configured output log level.

    Args:
        message_level: one of ('debug', 'info', 'warn', 'warning', 'error', 'critical')

    Returns:
        True if robocorp.log will print messages at this level to the console
        given the current output log level; False otherwise.
    """
    # Normalize common names
    lvl = (message_level or "").lower()
    if lvl == "error":
        lvl = "critical"
    if lvl == "warning":
        lvl = "warn"

    order = {
        'debug': 10,
        'info': 20,
        'warn': 30,
        'critical': 40,
        'none': 999,
    }

    configured = _OUTPUT_LOG_LEVEL or 'info'
    configured = configured.lower()
    configured_rank = order.get(configured, 20)
    message_rank = order.get(lvl, 20)

    return configured_rank <= message_rank


def get_logger(name: str = __name__):
    """
    Get a logger instance for compatibility with existing code.
    
    This is provided for gradual migration from standard logging.
    Returns a wrapper that uses Robocorp log methods.
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        Logger-like object that uses Robocorp logging
    
    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Processing job", job_id)
    """
    class RobocorpLogger:
        def __init__(self, logger_name: str):
            self.name = logger_name
            self._prefix = f"[{logger_name.split('.')[-1]}]"
        
        def info(self, msg: str, *args, **kwargs):
            log.info(f"{self._prefix} {msg}", *args, **kwargs)
        
        def debug(self, msg: str, *args, **kwargs):
            log.debug(f"{self._prefix} {msg}", *args, **kwargs)
        
        def warning(self, msg: str, *args, **kwargs):
            log.warn(f"{self._prefix} {msg}", *args, **kwargs)
        
        def warn(self, msg: str, *args, **kwargs):
            log.warn(f"{self._prefix} {msg}", *args, **kwargs)
        
        def error(self, msg: str, *args, **kwargs):
            # Map error to an error-level method and include the module prefix
            log.error(f"{self._prefix} {msg}", *args, **kwargs)
        
        def critical(self, msg: str, *args, **kwargs):
            log.critical(f"{self._prefix} {msg}", *args, **kwargs)
        
        def exception(self, msg: str = "", *args, **kwargs):
            if msg:
                log.exception(f"{self._prefix} {msg}", *args, **kwargs)
            else:
                log.exception()
    
    return RobocorpLogger(name)


def cleanup_logging() -> None:
    """
    Cleanup and close log outputs.
    
    This should be called at the end of your application to ensure
    all logs are flushed and the HTML report is generated.
    """
    log.info("=" * 80)
    log.info(f"[Robolog] Session ended: {datetime.now().isoformat()}")
    log.info("=" * 80)
    log.close_log_outputs()


# Context managers for sensitive operations
class suppress_sensitive_logging:
    """
    Context manager to suppress logging of sensitive operations.
    
    Use this when handling passwords, tokens, or other sensitive data.
    
    Example:
        >>> with suppress_sensitive_logging():
        >>>     password = input("Enter password: ")
        >>>     authenticate(username, password)
    """
    def __enter__(self):
        self._ctx = log.suppress_variables()
        return self._ctx.__enter__()
    
    def __exit__(self, *args):
        return self._ctx.__exit__(*args)


# Export main functions and classes
__all__ = [
    'log',
    'setup_logging',
    'cleanup_logging',
    'hide_sensitive_value',
    'get_logger',
    'suppress_sensitive_logging'
]
