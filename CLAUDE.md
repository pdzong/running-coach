# Running coach assistant

This project is a personal running coach assistant built on Polar Flow data. It downloads workouts,
analyses them with deterministic scripts, and supports discussing and adjusting training plans.

## Start of every training conversation

Read these before giving any training advice. They are personal and gitignored:

- `athlete/profile.md`: heart rate, zones, current paces, PRs, races, coaching situation
- `athlete/current-plan.md`: what the plan is right now and who owns it
- `athlete/journal.md`: recent events (injuries, illness, life), newest first
- `athlete/goals.md`
- When planning or judging sessions: `athlete/method.md`, `athlete/session-templates.md`, `athlete/history.md`

If `athlete/` is missing, say so and offer to restore it from the latest `data/backups/athlete-*.zip`
or the Google Drive backup.

## Skills

- `/sync`: download new sessions and refresh the dataset and planned targets
- `/review`: week or block review against the plan
- `/session`: analyse one workout
- `/adjust`: handle an injury, illness or life event and propose plan changes

## Commands

Windows, use `py -3`. Pure-Python only: pandas and other native-DLL packages are blocked by application control.

| Purpose | Command |
|---|---|
| Download new Polar sessions (last 31 days), then upload FIT files to Drive | `py -3 scripts/update_polar.py` (add `--headless` once signed in) |
| Full history download | `py -3 scripts/download_polar_history.py` |
| Session details (coach targets, phase results) | `py -3 scripts/fetch_polar.py details [--days N]` |
| Planned targets from the Polar calendar | `py -3 scripts/fetch_polar.py targets [--start D --end D]` |
| Rebuild the analysis dataset (incremental) | `py -3 scripts/analysis/build_dataset.py` |
| Weekly load and zones | `py -3 scripts/analysis/report.py weeks [--weeks N]` |
| Monthly zones and efficiency | `py -3 scripts/analysis/report.py months [--since YYYY-MM]` |
| Race-like efforts, PRs | `py -3 scripts/analysis/report.py races` |
| One session in detail | `py -3 scripts/analysis/report.py session YYYY-MM-DD [--all]` |
| Plan vs done | `py -3 scripts/analysis/report.py plan [--start D --days N]` |
| Back up athlete notes to Drive | `py -3 scripts/backup_athlete.py` |
| Upload FIT files to Drive | `py -3 scripts/upload_polar_drive.py` |

Prefer these scripts over ad hoc analysis so numbers stay consistent between sessions. If a new kind of
analysis is needed repeatedly, add it to `scripts/analysis/` rather than writing throwaway code.

## Data layout (all gitignored)

- `data/polar/*.FIT`, `data/polar/index.json` (Polar session id → file)
- `data/polar/details/{id}.json`: Polar analysis summary and details for a session
- `data/polar/targets/targets.json`: planned training targets (events and definitions)
- `data/analysis/sessions.json`, `data/analysis/traces.json`: built by `build_dataset.py`
- `athlete/`: personal notes and `profile.json` (hr_max, hr_rest, timezone used by the scripts)

## Rules

- Never ask for, type, read or store the Polar or Google password. The user signs in in the browser window
  the scripts open; sign-ins live in `.polar-profile/` and `.google-profile/`.
- The GitHub repo is public. Never commit `data/`, `athlete/`, `config/drive.json`, the browser profiles,
  or any personal analysis. Commit only when asked, as pull requests with conventional commit messages.
- When a script's Chrome must be killed, target only processes whose command line contains the profile
  directory, never the user's normal browser.
- Until the end of 2026 the human coach's TrainingPeaks plan is the source of truth. Do not rewrite it;
  analyse, flag concerns, and prepare notes or questions for the coach.
- Polar write endpoints (`POST /api/trainingtarget`) are known but untested. Do not call them without the
  user's explicit go-ahead, and test with one dummy future target first.
- Record notable events and decisions in `athlete/journal.md` (newest first) and keep `athlete/current-plan.md`
  current. After changing `athlete/`, run `py -3 scripts/backup_athlete.py`.
- Not a doctor: for pain that changes gait, persists, or worsens, recommend a physio or doctor.
