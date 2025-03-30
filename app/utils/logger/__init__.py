import asyncio  # For asynchronous exception handling
import json
import sys

from loguru import logger
from sentry_sdk import capture_exception
from sentry_sdk import init as sentry_init

from .types import FileConfig


def _json_formatter(record):
    """
    Custom JSON formatter for logging.
    """
    return json.dumps({
        "time": record["time"].strftime("%Y-%m-%d %H:%M:%S"),
        "level": record["level"].name,
        "file": record["file"].name,  # Include the file name
        "line": record["line"],       # Include the line number
        "name": record["name"],       # Include the logger name
        "module": record["module"],   # Include the module name
        "exception": record["exception"],  # Include exception details if any
        "message": record["message"],
        **record["extra"],            # Include additional context
    })


def setup_logging(debug_mode: bool = False, file_config: FileConfig = None, sentry_dsn: str = None, sentry_environment: str = None):
    """Configure logging for the application."""
    # Initialize Sentry if DSN is provided
    if sentry_dsn:
        env = sentry_environment or "test"
        sentry_init(dsn=sentry_dsn, environment=env)

    # Remove default handler
    logger.remove()

    # Determine minimum console log level based on debug mode
    console_level = "DEBUG" if debug_mode else "INFO"

    # Console handler with custom JSON formatting
    def console_sink(message):
        """
        Custom sink for console logging.
        """
        record = message.record
        formatted_message = _json_formatter(record)
        sys.stdout.write(formatted_message + "\n")

    logger.add(
        console_sink,
        level=console_level,
        backtrace=True,
        diagnose=True,
    )

    # Sentry handler for exceptions (asynchronous)
    async def async_capture_exception(exception):
        """
        Asynchronous task to send exceptions to Sentry.
        """
        capture_exception(exception)

    def sentry_sink(message):
        """
        Custom sink for sending exceptions to Sentry asynchronously.
        """
        record = message.record
        if record["exception"]:
            # Schedule the async task to send the exception to Sentry
            asyncio.create_task(async_capture_exception(record["exception"]))

    logger.add(
        sentry_sink,
        level="ERROR",  # Only send error-level logs to Sentry
        backtrace=True,
        diagnose=True,
    )

    if file_config is not None:
        # Ensure the directory exists
        file_config.ensure_directory_exists()

        # File handler for debug logs
        logger.add(
            file_config.debug_location,
            level="DEBUG",
            rotation=file_config.rotation,
            retention=file_config.retention,
            serialize=True,  # Serialize the log record to JSON
        )

        # File handler for error logs
        logger.add(
            file_config.error_location,
            level="ERROR",
            rotation=file_config.rotation,
            retention=file_config.retention,
            serialize=True,  # Serialize the log record to JSON
        )

__all__ = ["setup_logging", "FileConfig"]
