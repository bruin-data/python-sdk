import os
import shutil

import pytest


def _find_bruin():
    """Find the bruin binary, checking BRUIN_PATH env var first, then common locations."""
    # 1. Explicit env var
    explicit = os.environ.get("BRUIN_PATH")
    if explicit:
        return explicit

    # 2. Dev build from the sibling bruin repo
    repo_bin = os.path.join(os.path.dirname(__file__), "..", "..", "..", "bruin", "bin", "bruin")
    repo_bin = os.path.normpath(repo_bin)
    if os.path.isfile(repo_bin) and os.access(repo_bin, os.X_OK):
        return repo_bin

    # 3. System PATH
    system = shutil.which("bruin")
    if system:
        return system

    return None


@pytest.fixture(scope="session")
def bruin_bin():
    """Return the path to the bruin binary, or skip if not found."""
    path = _find_bruin()
    if path is None:
        pytest.skip("bruin binary not found — set BRUIN_PATH env var")
    return path
