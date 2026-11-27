---
name: sync
description: Download new Polar Flow sessions, refresh session details and planned targets, rebuild the analysis dataset, and summarise what is new. Use when the user asks to update, sync or pull workouts.
---

# Sync workouts

1. Download new sessions:
   `py -3 scripts/update_polar.py --headless`
   If it says Polar is not signed in, run `py -3 scripts/update_polar.py` without `--headless` and tell the
   user to sign in in the browser window that opens. Never handle the password.
   The script uploads new FIT files to Google Drive when that sign-in exists; if it reports Drive is not
   signed in, mention `py -3 scripts/upload_polar_drive.py` once, without blocking on it.
2. Fetch details for recent sessions: `py -3 scripts/fetch_polar.py details`
3. Refresh planned targets: `py -3 scripts/fetch_polar.py targets`
4. Rebuild the dataset: `py -3 scripts/analysis/build_dataset.py`
5. Show what happened: `py -3 scripts/analysis/report.py plan --days 14` and
   `py -3 scripts/analysis/report.py weeks --weeks 4`.
6. Summarise for the user in a few sentences: new sessions, whether they matched the planned targets,
   anything unusual (missed sessions, much higher heart rate than usual for the pace, very long or short runs),
   and what is planned next. Read `athlete/current-plan.md` and the latest `athlete/journal.md` entries first
   so the summary is in context.
7. If the user explains something (felt ill, skipped because of travel), add a dated entry to
   `athlete/journal.md` and run `py -3 scripts/backup_athlete.py`.
