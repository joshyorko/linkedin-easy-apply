"""Keep mutable runtime files separate from immutable application source."""
import os
from pathlib import Path


def runtime_path(path: str | Path) -> Path:
    value = Path(path)
    state_root = os.getenv("EASY_APPLY_STATE_DIR")
    if state_root and not value.is_absolute():
        return Path(state_root) / value
    return value
