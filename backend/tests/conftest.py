"""
Shared fixtures for OMI-TED v2 tests.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure backend/ is on sys.path so `from services.xxx import ...` works
_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)
