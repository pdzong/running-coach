---
name: adjust
description: Handle unplanned events - injury, pain, illness, travel, work or family events, missed sessions - by recording them and proposing how to adjust the training plan. Use when the user reports something that disrupts training.
---

# Adjust the plan for an event

1. Read `athlete/current-plan.md`, `athlete/journal.md`, `athlete/goals.md` and the disruption guidelines at the
   end of `athlete/session-templates.md`.
2. Understand the event. Ask only what changes the decision:
   - Injury or pain: where, since when, during or after running, does it change your stride, does it persist
     the next day, getting better or worse.
   - Illness: fever, chest or only above the neck, days off so far.
   - Life events or travel: dates, what is possible (time per day, treadmill, terrain).
3. Safety first: pain that changes gait, persists or worsens, swelling, or any chest symptoms → recommend
   stopping running and seeing a physio or doctor. Do not diagnose.
4. Check recent load for context: `py -3 scripts/analysis/report.py weeks --weeks 6` and
   `py -3 scripts/analysis/report.py plan --days 14`.
5. Propose an adjustment with a short reason for each change: which sessions to drop, shorten, swap or move,
   how to return (easy only first, then strides, then reduced quality), and what to watch. Keep the block's
   intent where possible; never stack missed sessions.
6. While the coach owns the plan (until end of 2026 or as stated in current-plan.md), present the proposal as
   a note for the coach and a suggestion for the user, not a rewrite of the coach's plan.
7. After the user agrees: add a dated entry to `athlete/journal.md` (event, decision, why), update
   `athlete/current-plan.md` if the plan changed, and run `py -3 scripts/backup_athlete.py`.
