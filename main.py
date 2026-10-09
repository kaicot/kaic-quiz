"""Run Quiz Reporter from source (``python main.py``) or as the packaged EXE's entry point."""

import sys
from pathlib import Path

source = Path(__file__).resolve().parent / "src"
if source.is_dir() and str(source) not in sys.path:
    sys.path.insert(0, str(source))

from quiz_reporter.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
