---
name: review
description: Review a training week, block or longer period against the plan and history - volume, intensity distribution, quality sessions, efficiency trend, and flags. Use when the user asks how training is going, for a weekly review, or before talking to the coach.
---

# Training review

Read `athlete/profile.md`, `athlete/current-plan.md`, `athlete/journal.md` and `athlete/method.md` first.
If the data may be stale, offer `/sync` first.

## Gather

- `py -3 scripts/analysis/report.py weeks --weeks 8` (volume, long run, TRIMP, gym, zone shares)
- `py -3 scripts/analysis/report.py plan --start <first day> --days <n>` (planned vs done, target names)
- `py -3 scripts/analysis/report.py months --since <YYYY-MM>` for block-level trends and efficiency
- `py -3 scripts/analysis/report.py session <date>` for each quality session in the period

## Assess

- Compliance: planned sessions done, missed or changed.
- Load: week-to-week change (more than ~10-15% up for several weeks without a lighter week is a flag);
  lighter week every 3-4 weeks.
- Intensity distribution: easy days should stay in the easy heart-rate range from profile.md; watch for
  easy days drifting into zone 3 (history.md says whether that has been a habit).
- Quality sessions: did reps hit target pace at a reasonable heart rate; was the last rep similar to the first;
  compare with the same session type earlier in the block (method.md progressions).
- Efficiency: pace at hr 130-140 against previous months.
- Context from the journal (illness, travel, sleep).

## Report

Lead with a one-line verdict. Then what went well, what to watch, and concrete suggestions. While the coach
owns the plan, phrase changes as questions or notes for the coach. Offer to add notable conclusions to
`athlete/journal.md`.
