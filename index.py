"""Vercel entrypoint.

Vercel looks for a FastAPI instance named `app` in a root-level index.py.
The real app lives in backend/main.py; this file just makes it importable.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "backend"))

from main import app  # noqa: E402,F401
