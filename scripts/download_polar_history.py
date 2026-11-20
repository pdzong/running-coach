"""Download every Polar Flow session that is not already saved.

Opens the same signed-in browser as extract_polar_fit.py. Sessions already
listed in data/polar/index.json are skipped. Newly saved files are copied to
Google Drive when that sign-in already exists.

  py -3 scripts/download_polar_history.py
  py -3 scripts/download_polar_history.py --dry-run
  py -3 scripts/download_polar_history.py --headless
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

target = Path(__file__).with_name("extract_polar_fit.py")
sys.argv = [str(target), "--all", *sys.argv[1:]]
runpy.run_path(str(target), run_name="__main__")
