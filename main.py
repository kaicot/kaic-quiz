"""Run Quiz Reporter from source (``python main.py``) or as the packaged EXE's entry point.

The splash goes up first, before the rest of the program is imported, so a click on the EXE
shows something at once.
"""

import sys
from pathlib import Path

source = Path(__file__).resolve().parent / "src"
if source.is_dir() and str(source) not in sys.path:
    sys.path.insert(0, str(source))


def run() -> int:
    if "--self-check" in sys.argv:  # hidden check of a built program: no window at all
        from quiz_reporter.app import main

        return main()
    from quiz_reporter.startup_splash import show_splash

    application, splash = show_splash(sys.argv)
    from quiz_reporter.app import main

    return main(application=application, splash=splash)


if __name__ == "__main__":
    raise SystemExit(run())
