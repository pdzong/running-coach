"""Plain-text training reports from the analysis dataset.

  py -3 scripts/analysis/report.py weeks --weeks 8
  py -3 scripts/analysis/report.py months --since 2025-01
  py -3 scripts/analysis/report.py efficiency --since 2025-01
  py -3 scripts/analysis/report.py races
  py -3 scripts/analysis/report.py session 2026-11-22
  py -3 scripts/analysis/report.py plan --days 14

Run build_dataset.py first so new FIT files are included.
"""

from __future__ import annotations

import argparse
import collections
import json
from datetime import date, datetime, timedelta

import fitdecode

from common import (
    ANALYSIS_DIR,
    DETAILS_DIR,
    POLAR_DIR,
    RACE_DISTANCES,
    TARGETS_FILE,
    clock,
    is_run,
    load_json,
    load_profile,
    pace,
    pace_from,
    trimp,
    utf8_stdout,
    zone_bounds,
    zone_of,
)

# Minimum average heart rate over a best segment, as a share of max, for a race-level effort.
RACE_HR_SHARE = {"5k": 0.89, "10k": 0.875, "HM": 0.86, "M": 0.80}
LABEL = {"5k": "5 km", "10k": "10 km", "HM": "Half marathon", "M": "Marathon"}


def sessions() -> list[dict]:
    return load_json(ANALYSIS_DIR / "sessions.json")


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def zone_shares(counter: collections.Counter) -> str:
    total = sum(counter[z] for z in range(6)) or 1
    low = 100 * (counter[0] + counter[1] + counter[2]) / total
    return f"{low:5.0f} {100 * counter[3] / total:4.0f} {100 * counter[4] / total:4.0f} {100 * counter[5] / total:4.0f}"


def cmd_weeks(args, profile) -> None:
    hr_max, hr_rest = profile["hr_max"], profile["hr_rest"]
    first = date.fromisoformat(args.since) if args.since else monday_of(date.today()) - timedelta(weeks=args.weeks - 1)
    weeks: dict[date, collections.Counter] = collections.OrderedDict()
    zones: dict[date, collections.Counter] = collections.defaultdict(collections.Counter)
    for s in sessions():
        day = datetime.fromisoformat(s["start"]).date()
        if day < first:
            continue
        week = weeks.setdefault(monday_of(day), collections.Counter())
        week["trimp"] += trimp(s["hr_hist_5"], hr_max, hr_rest)
        if is_run(s):
            km = (s["distance_m"] or 0) / 1000
            week["runs"] += 1
            week["km"] += km
            week["long"] = max(week["long"], km)
            week["run_h"] += (s["timer_s"] or 0) / 3600
            for bucket, seconds in s["hr_hist_5"].items():
                zones[monday_of(day)][zone_of(int(bucket) + 2.5, hr_max)] += seconds
        elif s.get("sub_sport") == "strength_training" or s.get("sport") in ("training", "generic"):
            week["gym"] += 1
        else:
            week["other"] += 1
    print("Run time share by zone uses max heart rate", hr_max, "zones", zone_bounds(hr_max))
    print("week of      runs    km  long  run h  TRIMP  gym  other | z1-2%  z3%  z4%  z5%")
    for monday, w in weeks.items():
        print(
            f"{monday}  {w['runs']:4d} {w['km']:5.0f} {w['long']:5.1f} {w['run_h']:6.1f} {w['trimp']:6.0f} "
            f"{w['gym']:4d} {w['other']:6d} | {zone_shares(zones[monday])}"
        )


def efficiency_by_month(since: str, low: int, high: int) -> dict[str, tuple[float, int]]:
    traces = load_json(ANALYSIS_DIR / "traces.json")
    speeds: dict[str, list[float]] = collections.defaultdict(list)
    for s in sessions():
        if not is_run(s) or s["start"][:7] < since or s["file"] not in traces:
            continue
        for t, hr, speed, _alt, _cad, _dist in traces[s["file"]]:
            if t >= 600 and hr is not None and speed and speed >= 2.2 and low <= hr <= high:
                speeds[s["start"][:7]].append(speed)
    out = {}
    for month, values in speeds.items():
        if len(values) >= 60:
            values.sort()
            out[month] = (values[len(values) // 2], len(values))
    return out


def cmd_months(args, profile) -> None:
    hr_max = profile["hr_max"]
    months: dict[str, collections.Counter] = collections.OrderedDict()
    zones: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for s in sessions():
        month = s["start"][:7]
        if month < args.since or not is_run(s):
            continue
        m = months.setdefault(month, collections.Counter())
        m["runs"] += 1
        m["km"] += (s["distance_m"] or 0) / 1000
        m["h"] += (s["timer_s"] or 0) / 3600
        for bucket, seconds in s["hr_hist_5"].items():
            zones[month][zone_of(int(bucket) + 2.5, hr_max)] += seconds
    eff = efficiency_by_month(args.since, args.low, args.high)
    print(f"Efficiency = median pace at heart rate {args.low}-{args.high}, after the first 10 minutes")
    print("month    runs    km  hours | z1-2%  z3%  z4%  z5% | efficiency")
    for month, m in months.items():
        e = eff.get(month)
        print(
            f"{month}  {m['runs']:4d} {m['km']:5.0f} {m['h']:6.1f} | {zone_shares(zones[month])} | "
            f"{pace(e[0]) + '/km' if e else '-'}"
        )


def cmd_efficiency(args, profile) -> None:
    eff = efficiency_by_month(args.since, args.low, args.high)
    print(f"Median pace of 10-second samples at heart rate {args.low}-{args.high}, after the first 10 minutes")
    for month in sorted(eff):
        speed, count = eff[month]
        print(f"{month}  {pace(speed)}/km  samples {count}")


def cmd_races(args, profile) -> None:
    hr_max = profile["hr_max"]
    all_sessions = [s for s in sessions() if is_run(s) and s.get("best")]
    for key, length in RACE_DISTANCES.items():
        km = length / 1000
        efforts = [(datetime.fromisoformat(s["start"]), s, s["best"][key]) for s in all_sessions if key in s["best"]]
        print(f"\n== {LABEL[key]}: race-like efforts (average heart rate >= {round(RACE_HR_SHARE[key] * hr_max)}, "
              f"fastest within {args.window} days either side)")
        for when, s, b in efforts:
            if not b["hr"] or b["hr"] < RACE_HR_SHARE[key] * hr_max:
                continue
            if b["sec"] > min(x["sec"] for w, _, x in efforts if abs((w - when).days) <= args.window):
                continue
            inside = b["from_km"] >= 0.8 or (s["distance_m"] or 0) / 1000 > km * 1.12
            print(
                f"{s['start'][:10]}  {clock(b['sec']):>8}  {pace_from(b['sec'], km)}/km  hr {b['hr']}  "
                f"from km {b['from_km']:5.2f} of {(s['distance_m'] or 0) / 1000:5.1f}  "
                f"{'inside a longer recording' if inside else 'own recording'}"
            )
        top = sorted(efforts, key=lambda e: e[2]["sec"])[: args.top]
        print(f"   fastest {args.top} ever: " + ", ".join(f"{clock(b['sec'])} ({s['start'][:10]})" for _, s, b in top))
    print("\nCheck candidates with `report.py session DATE`: a race shows a warm-up, a standstill at the start, "
          "then a steady hard effort that ends with the recording. Tempo runs are followed by a cool-down.")


def fit_records(file_name: str) -> list[tuple]:
    rows = []
    with fitdecode.FitReader(str(POLAR_DIR / file_name), check_crc=fitdecode.CrcCheck.DISABLED) as reader:
        for frame in reader:
            if isinstance(frame, fitdecode.FitDataMessage) and frame.name == "record":
                values = {f.name: f.value for f in frame.fields}
                if values.get("timestamp") and values.get("distance") is not None:
                    rows.append((values["timestamp"].timestamp(), float(values["distance"]), values.get("heart_rate"),
                                 values.get("enhanced_altitude", values.get("altitude"))))
    return rows


def polar_id_for(file_name: str) -> str | None:
    index = load_json(POLAR_DIR / "index.json", default={})
    for session_id, entry in index.items():
        if entry.get("file") == file_name:
            return session_id
    return None


def completed_target_names(file_name: str) -> list[str]:
    session_id = polar_id_for(file_name)
    path = DETAILS_DIR / f"{session_id}.json" if session_id else None
    if not path or not path.exists():
        return []
    targets = (json.loads(path.read_text(encoding="utf-8")).get("details") or {}).get("exerciseResultTargetData") or {}
    return [t.get("name") for t in targets.values() if t.get("name")]


def describe_phases(phases: list[dict], indent: str = "    ") -> list[str]:
    lines = []
    for phase in phases:
        if phase.get("phaseType") == "REPEAT":
            lines.append(f"{indent}repeat {phase.get('repeatCount')} x")
            lines += describe_phases(phase.get("phases") or [], indent + "  ")
            continue
        goal = f"{phase['distance']} m" if phase.get("goalType") == "DISTANCE" else phase.get("duration")
        zone = phase.get("intensityType", "").replace("_", " ").lower()
        lines.append(f"{indent}{phase.get('name')}: {goal}, {zone} {phase.get('lowerZone')}-{phase.get('upperZone')}")
    return lines


def cmd_session(args, profile) -> None:
    hr_max = profile["hr_max"]
    matches = [s for s in sessions() if s["start"].startswith(args.date)]
    if not matches:
        raise SystemExit(f"No session on {args.date}. Run build_dataset.py if it was synced recently.")
    for s in matches if args.all else [matches[min(args.index, len(matches) - 1)]]:
        km = (s["distance_m"] or 0) / 1000
        print(f"\n{s['start'][:16]}  {s['sport']}/{s.get('sub_sport')}  {km:.2f} km  moving {clock(s['timer_s'] or 0)}  "
              f"elapsed {clock(s['elapsed_s'] or 0)}  pace {pace(s['avg_speed'])}  hr {s['avg_hr']}/{s['max_hr']}  "
              f"ascent {s.get('ascent')} m  file {s['file']}")
        if len(matches) > 1 and not args.all:
            print(f"  ({len(matches)} sessions that day; use --index N or --all)")
        zones = collections.Counter()
        for bucket, seconds in s["hr_hist_5"].items():
            zones[zone_of(int(bucket) + 2.5, hr_max)] += seconds
        total = sum(zones.values()) or 1
        print("  time in zone: " + "  ".join(f"z{z} {100 * zones[z] / total:.0f}%" for z in range(1, 6)))
        for key, b in (s.get("best") or {}).items():
            print(f"  fastest {LABEL[key]}: {clock(b['sec'])} ({pace_from(b['sec'], RACE_DISTANCES[key] / 1000)}/km) "
                  f"hr {b['hr']} from km {b['from_km']}")

        session_id = polar_id_for(s["file"])
        detail_path = DETAILS_DIR / f"{session_id}.json" if session_id else None
        if detail_path and detail_path.exists():
            detail = json.loads(detail_path.read_text(encoding="utf-8"))
            summary = detail.get("summary") or {}
            targets = (detail.get("details") or {}).get("exerciseResultTargetData") or {}
            for target in targets.values():
                print(f"  planned target: {target.get('name')} ({target.get('type')}), reached: {target.get('targetReached')}")
                for rep in target.get("exercisePhaseRepetitionModels") or []:
                    speed = (rep.get("speedStatistic") or {}).get("avg")
                    hr = (rep.get("heartRateStatistic") or {}).get("avg")
                    print(f"    phase {rep.get('phaseIndex')} rep {rep.get('phaseRepetitionIndex')}: "
                          f"{rep.get('distance')} m in {rep.get('duration')}, "
                          f"{pace(speed / 3.6) if speed else '-'}/km, hr {hr}")
            extras = {k: summary.get(k) for k in ("feeling", "note", "trainingBenefit") if summary.get(k)}
            if extras:
                print(f"  Polar notes: {extras}")

        if any(abs((lap["d"] or 0) - 1000) > 15 for lap in s["laps"][:-1]):
            print("  laps (manual or phase):")
            for n, lap in enumerate(s["laps"], 1):
                print(f"    {n:2d}. {(lap['d'] or 0) / 1000:5.2f} km  {clock(lap['t'] or 0):>7}  "
                      f"{pace(lap['v'])}/km  hr {lap['hr']}/{lap['maxhr']}  ({lap.get('trigger')})")
        rows = fit_records(s["file"])
        if not rows:
            continue
        print("  per km (pace/avg hr; a long km means a stop):")
        splits, km_mark, start = [], 1, 0
        for i, row in enumerate(rows):
            if row[1] >= km_mark * 1000 or i == len(rows) - 1:
                dist = (row[1] - rows[start][1]) / 1000
                if dist > 0.2:
                    hrs = [r[2] for r in rows[start:i + 1] if r[2]]
                    splits.append(f"{km_mark:2d}: {pace_from(row[0] - rows[start][0], dist)}/{round(sum(hrs) / len(hrs)) if hrs else '-'}")
                km_mark, start = km_mark + 1, i
        for i in range(0, len(splits), 6):
            print("    " + "   ".join(splits[i:i + 6]))


def cmd_plan(args, profile) -> None:
    payload = load_json(TARGETS_FILE, default={"events": [], "targets": {}})
    if not payload["events"]:
        raise SystemExit("No planned targets saved. Run: py -3 scripts/fetch_polar.py targets")
    first = date.fromisoformat(args.start) if args.start else date.today() - timedelta(days=7)
    last = first + timedelta(days=args.days - 1)
    done = collections.defaultdict(list)
    for s in sessions():
        done[s["start"][:10]].append(s)
    print(f"Planned targets from {first} to {last} (saved {payload.get('fetched', 'unknown')})")
    day = first
    events = sorted(payload["events"], key=lambda e: e["datetime"])
    while day <= last:
        key = day.isoformat()
        planned = [e for e in events if e["datetime"].startswith(key)]
        completed = done.get(key, [])
        if planned or completed:
            print(f"\n{key} {day.strftime('%a')}")
        for event in planned:
            target = payload["targets"].get(str(event.get("ListItemId") or event.get("listItemId"))) or {}
            source = event.get("externalSource") or "Polar"
            print(f"  plan [{source}] {event['title']}")
            if event.get("description"):
                for line in event["description"].splitlines():
                    if line.strip():
                        print(f"     | {line.strip()}")
            for exercise in target.get("exerciseTargets") or []:
                if exercise.get("duration") or exercise.get("distance"):
                    print(f"     total: {exercise.get('duration') or ''} {str(exercise['distance']) + ' m' if exercise.get('distance') else ''}")
                for line in describe_phases(exercise.get("phases") or [], "     "):
                    print(line)
        for s in completed:
            names = completed_target_names(s["file"])
            print(f"  done {s['sport']}: {(s['distance_m'] or 0) / 1000:.1f} km, {clock(s['timer_s'] or 0)}, "
                  f"pace {pace(s['avg_speed'])}, hr {s['avg_hr']}"
                  + (f"  (target: {'; '.join(names)})" if names else ""))
        day += timedelta(days=1)


def main() -> int:
    utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("weeks", help="Weekly volume, load and zones")
    p.add_argument("--weeks", type=int, default=8)
    p.add_argument("--since", help="First day, YYYY-MM-DD (overrides --weeks)")

    for name, text in (("months", "Monthly volume, zones and efficiency"), ("efficiency", "Pace at a fixed heart rate")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--since", default=f"{date.today().year - 1}-01", help="First month, YYYY-MM")
        p.add_argument("--low", type=int, default=130)
        p.add_argument("--high", type=int, default=140)

    p = sub.add_parser("races", help="Race-like efforts, including ones hidden inside longer recordings")
    p.add_argument("--window", type=int, default=60, help="Days either side for the fastest-in-period check")
    p.add_argument("--top", type=int, default=5)

    p = sub.add_parser("session", help="One session in detail")
    p.add_argument("date", help="YYYY-MM-DD")
    p.add_argument("--index", type=int, default=0, help="Which session that day, from 0")
    p.add_argument("--all", action="store_true", help="Every session that day")

    p = sub.add_parser("plan", help="Planned targets next to what was done")
    p.add_argument("--start", help="First day, YYYY-MM-DD. Default: a week ago")
    p.add_argument("--days", type=int, default=21)

    args = parser.parse_args()
    profile = load_profile()
    {
        "weeks": cmd_weeks,
        "months": cmd_months,
        "efficiency": cmd_efficiency,
        "races": cmd_races,
        "session": cmd_session,
        "plan": cmd_plan,
    }[args.command](args, profile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
