"""Private scratch directories for root tests.

``tempfile.mkdtemp`` can create an ACL that a restricted Windows token cannot
write. Tests only need a private directory that is cleaned up afterwards, so
create it under the git-ignored ``tmp/`` directory.
"""

from __future__ import annotations

import os
import shutil
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def scratch_directory(name: str):
    """Yield a writable, project-local scratch directory for one test."""

    path = ROOT / "tmp" / f"{name}_{os.getpid()}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
