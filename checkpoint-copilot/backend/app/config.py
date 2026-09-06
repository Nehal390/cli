"""Configuration for Checkpoint Copilot.

Reads settings from environment variables. Defaults point at the current
repository for the demo, but can be overridden via `ENTIRE_REPO_PATH`.
"""
import os
from pathlib import Path

# Default to the parent directory (the Entire CLI repo) so the demo works
# out-of-the-box when the developer runs it from inside their workspace.
# Demo checkpoint marker: confirms live checkpoint detection on config changes.
_DEFAULT_REPO_PATH = str(Path(__file__).resolve().parents[3])


def get_repo_path() -> str:
    """Get the path to the Entire-enabled repo to analyze.

    Override with ENTIRE_REPO_PATH environment variable.
    """
    return os.environ.get("ENTIRE_REPO_PATH", _DEFAULT_REPO_PATH)
