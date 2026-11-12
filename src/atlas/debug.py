"""Debug logging utilities for ATLAS."""
import sys
from .config import is_voice_debug_enabled


def debug_log(message: str, category: str = "debug") -> None:
    """Unified debug logging function for ATLAS.

    Args:
        message: The debug message to log
        category: The log category (e.g., "debug", "voice", "echo", "tts", etc.)
    """
    if not is_voice_debug_enabled():
        return
    try:
        print(f"[{category:^10}] {message}", file=sys.stderr)
    except Exception:
        pass
