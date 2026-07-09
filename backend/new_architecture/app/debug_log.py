"""
Debug logging helpers gated by DEBUG_LOGGING for production Pi deployments.
"""

import os

# True when verbose pipeline logs are enabled (set DEBUG_LOGGING=true in .env).
DEBUG_LOGGING = os.getenv("DEBUG_LOGGING", "false").lower() in ("1", "true", "yes")


def debug_log(*args, **kwargs) -> None:
    """Print only when DEBUG_LOGGING is enabled to avoid hot-path I/O on constrained hardware."""
    if DEBUG_LOGGING:
        print(*args, **kwargs)
