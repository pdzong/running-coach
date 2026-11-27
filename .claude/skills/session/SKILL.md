---
name: session
description: Analyse a single workout - pacing, heart rate, laps and phases against the planned target, and how it compares with similar earlier sessions. Use when the user asks about a specific run, race or workout.
---

# Session analysis

1. If the session may not be in the dataset yet, run `py -3 scripts/fetch_polar.py details` and
   `py -3 scripts/analysis/build_dataset.py`.
2. `py -3 scripts/analysis/report.py session <YYYY-MM-DD>` (`--all` when there were several sessions).
   It prints the summary, time in zone, fastest 5/10/21.1/42.2 km segments, the planned target with per-phase
   results when Polar has it, non-standard laps, and per-km splits. A very slow "km" means a stop.
3. Read `athlete/profile.md` for current paces and zones, and the target description from
   `report.py plan --start <date> --days 1` if the target text matters.
4. Compare with similar sessions: find earlier dates with the same target name or structure
   (`report.py plan` over a longer range shows target names) and run `report.py session` on one or two of them.
5. Explain in plain language: did it match the intent (easy stayed easy, reps on pace, even splits), heart-rate
   drift across reps, warm-up and cool-down, anything that suggests fatigue or improved fitness.
6. For races: use the fastest segment for the race distance; a warm-up, a long stop at the start and a hard
   effort to the end of the recording means the race was recorded together with the warm-up. Update the race
   lists and PRs in `athlete/profile.md` if this is a new result, add a journal entry, and run
   `py -3 scripts/backup_athlete.py`.
