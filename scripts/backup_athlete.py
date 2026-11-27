"""Back up the personal athlete/ notes to Google Drive.

Zips athlete/ into data/backups/athlete-YYYYMMDD-HHMM.zip and uploads backups
that are not in the Drive folder yet, using the sign-in from
upload_polar_drive.py. Each backup gets a new name, so older ones are kept.

  py -3 scripts/backup_athlete.py
  py -3 scripts/backup_athlete.py --no-upload
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ATHLETE_DIR = ROOT / "athlete"
BACKUP_DIR = ROOT / "data" / "backups"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-upload", action="store_true", help="Only create the zip")
    args = parser.parse_args()

    if not ATHLETE_DIR.exists():
        raise SystemExit("No athlete/ folder to back up.")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    archive = BACKUP_DIR / f"athlete-{datetime.now():%Y%m%d-%H%M}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(ATHLETE_DIR.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(ROOT))
    print(f"Saved {archive.relative_to(ROOT)}", flush=True)
    if args.no_upload:
        return 0
    script = Path(__file__).with_name("upload_polar_drive.py")
    completed = subprocess.run(
        [sys.executable, str(script), "--dir", str(BACKUP_DIR), "--glob", "athlete-*.zip", "--if-authorized"]
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
