"""Download Polar Flow sessions synced since the last check.

Asks Polar for the last 31 days and saves any session that is not already in
data/polar/index.json. Older backfill belongs in download_polar_history.py.
New FIT files are then copied to Google Drive when that sign-in already exists.

  py -3 scripts/update_polar.py
  py -3 scripts/update_polar.py --dry-run
  py -3 scripts/update_polar.py --headless
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

target = Path(__file__).with_name("extract_polar_fit.py")
sys.argv = [str(target), "--recent", *sys.argv[1:]]
runpy.run_path(str(target), run_name="__main__")
