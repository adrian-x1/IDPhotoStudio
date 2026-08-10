"""Run the test suite under a watchdog that reports where it hung.

A test that deadlocks on CI otherwise burns the six-hour job limit while
telling us nothing: the runner's stdout is block-buffered, so the name of the
test that stopped never reaches the log.  Unbuffered output plus a faulthandler
timer turns that silence into a stack trace for every live thread.
"""

from __future__ import annotations

import faulthandler
from pathlib import Path
import sys
import unittest


# Well past the ~1 minute the suite needs on a cold CI runner, far below the
# six-hour job ceiling.
HANG_TIMEOUT_SECONDS = 420

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = PROJECT_ROOT / "tests"


def main() -> int:
    # Running as a script puts scripts/ on the path instead of the project
    # root, which `python -m unittest` would have provided.
    for path in (PROJECT_ROOT, TESTS_DIR):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

    faulthandler.enable()
    faulthandler.dump_traceback_later(HANG_TIMEOUT_SECONDS, exit=True)

    suite = unittest.TestLoader().discover(
        str(TESTS_DIR),
        top_level_dir=str(TESTS_DIR),
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)

    faulthandler.cancel_dump_traceback_later()
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
