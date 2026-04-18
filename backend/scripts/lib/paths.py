"""Shared sys.path bootstrap for runner scripts under backend/scripts/."""

from __future__ import annotations

import os
import sys


def init_script_paths(caller_file: str) -> tuple[str, str, str]:
    """Insert scripts/ and backend/ on sys.path. Return (scripts_dir, backend_dir, project_root)."""
    scripts_dir = os.path.dirname(os.path.abspath(caller_file))
    backend_dir = os.path.abspath(os.path.join(scripts_dir, '..'))
    project_root = os.path.abspath(os.path.join(backend_dir, '..'))
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    return scripts_dir, backend_dir, project_root
