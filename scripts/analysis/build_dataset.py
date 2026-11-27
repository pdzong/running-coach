"""Turn the downloaded FIT files into the analysis dataset.

Writes data/analysis/sessions.json (one summary per session, with laps, a
heart-rate histogram and, for runs, the fastest continuous 5 km, 10 km, half
marathon and marathon) and data/analysis/traces.json (10-second samples for
recent sessions). Only files not in the dataset yet are parsed unless --rebuild.

  py -3 scripts/analysis/build_dataset.py
  py -3 scripts/analysis/build_dataset.py --rebuild
"""

from __future__ import annotations

import argparse
import math
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path

import fitdecode

from common import ANALYSIS_DIR, POLAR_DIR, RACE_DISTANCES, load_json, load_profile, local_zone, utf8_stdout, write_json

SESSIONS_FILE = ANALYSIS_DIR / "sessions.json"
TRACES_FILE = ANALYSIS_DIR / "traces.json"


def clean(values: dict, tz) -> dict:
    out = {}
    for key, value in values.items():
        if value is None or key.startswith("unknown"):
            continue
        if hasattr(value, "isoformat"):
            value = value.astimezone(tz).isoformat() if getattr(value, "tzinfo", None) else value.isoformat()
        elif isinstance(value, float) and math.isnan(value):
            continue
        elif isinstance(value, tuple):
            value = list(value)
        out[key] = value
    return out


def best_segments(records: list[tuple]) -> dict:
    """Fastest continuous stretch of each race distance, by watch distance."""
    rows = [(r[0], float(r[5]), r[1]) for r in records if r[5] is not None]
    if len(rows) < 60:
        return {}
    start = rows[0][0]
    total = rows[-1][1]
    best = {}
    for key, length in RACE_DISTANCES.items():
        if total < length:
            continue
        top = None
        j = 0
        for i in range(len(rows)):
            while j < len(rows) and rows[j][1] - rows[i][1] < length:
                j += 1
            if j >= len(rows):
                break
            seconds = rows[j][0] - rows[i][0]
            if top is None or seconds < top[0]:
                top = (seconds, i, j)
        if top:
            seconds, i, j = top
            hrs = [r[2] for r in rows[i:j + 1] if r[2]]
            best[key] = {
                "sec": round(seconds),
                "hr": round(sum(hrs) / len(hrs)) if hrs else None,
                "from_km": round(rows[i][1] / 1000, 2),
                "from_min": round((rows[i][0] - start) / 60, 1),
            }
    return best


def parse(path_str: str, timezone: str, trace_since: str) -> dict:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(timezone)
    path = Path(path_str)
    session: dict = {}
    laps: list[dict] = []
    records: list[tuple] = []
    try:
        with fitdecode.FitReader(path_str, check_crc=fitdecode.CrcCheck.DISABLED) as reader:
            for frame in reader:
                if not isinstance(frame, fitdecode.FitDataMessage):
                    continue
                if frame.name == "record":
                    values = {f.name: f.value for f in frame.fields}
                    ts = values.get("timestamp")
                    if ts is None:
                        continue
                    records.append((
                        ts.timestamp(),
                        values.get("heart_rate"),
                        values.get("enhanced_speed", values.get("speed")),
                        values.get("enhanced_altitude", values.get("altitude")),
                        values.get("cadence"),
                        values.get("distance"),
                    ))
                elif frame.name == "session" and not session:
                    session = clean({f.name: f.value for f in frame.fields}, tz)
                elif frame.name == "lap":
                    laps.append(clean({f.name: f.value for f in frame.fields}, tz))
    except Exception as exc:  # noqa: BLE001
        return {"file": path.name, "error": str(exc)}

    start = session.get("start_time")
    item = {
        "file": path.name,
        "start": start,
        "sport": session.get("sport"),
        "sub_sport": session.get("sub_sport"),
        "timer_s": session.get("total_timer_time"),
        "elapsed_s": session.get("total_elapsed_time"),
        "distance_m": session.get("total_distance"),
        "avg_hr": session.get("avg_heart_rate"),
        "max_hr": session.get("max_heart_rate"),
        "avg_speed": session.get("enhanced_avg_speed", session.get("avg_speed")),
        "ascent": session.get("total_ascent"),
        "calories": session.get("total_calories"),
        "avg_cadence": session.get("avg_running_cadence", session.get("avg_cadence")),
        "laps": [
            {
                "t": lap.get("total_timer_time"),
                "d": lap.get("total_distance"),
                "hr": lap.get("avg_heart_rate"),
                "maxhr": lap.get("max_heart_rate"),
                "v": lap.get("enhanced_avg_speed", lap.get("avg_speed")),
                "trigger": lap.get("lap_trigger"),
            }
            for lap in laps
        ],
        "best": best_segments(records) if session.get("sport") == "running" else {},
    }
    hist: dict[int, int] = {}
    for record in records:
        if record[1]:
            bucket = int(record[1] // 5 * 5)
            hist[bucket] = hist.get(bucket, 0) + 1
    item["hr_hist_5"] = hist

    trace = None
    if start and start >= trace_since and records:
        t0 = records[0][0]
        bins: dict[int, list] = {}
        for ts, hr, speed, alt, cad, dist in records:
            bins.setdefault(int((ts - t0) // 10), []).append((hr, speed, alt, cad, dist))
        trace = []
        for key in sorted(bins):
            rows = bins[key]

            def mean(idx: int):
                vals = [row[idx] for row in rows if row[idx] is not None]
                return round(sum(vals) / len(vals), 3) if vals else None

            trace.append([key * 10, mean(0), mean(1), mean(2), mean(3), rows[-1][4]])
    return {"summary": item, "trace": trace}


def main() -> int:
    utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rebuild", action="store_true", help="Parse every FIT file again")
    parser.add_argument(
        "--trace-since",
        default="2025-01-01",
        help="Keep 10-second traces for sessions from this date (default 2025-01-01)",
    )
    args = parser.parse_args()
    profile = load_profile()

    existing = [] if args.rebuild else load_json(SESSIONS_FILE, default=[])
    traces = {} if args.rebuild else load_json(TRACES_FILE, default={})
    known = {s["file"]: s for s in existing if "best" in s}
    files = sorted(str(p) for p in POLAR_DIR.glob("*.FIT") if p.name not in known)
    print(f"{len(known)} session(s) already in the dataset, {len(files)} FIT file(s) to parse.", flush=True)

    summaries = list(known.values())
    errors = 0
    if files:
        work = partial(parse, timezone=str(local_zone(profile)), trace_since=args.trace_since)
        with ProcessPoolExecutor() as pool:
            for result in pool.map(work, files, chunksize=8):
                if "error" in result:
                    errors += 1
                    print(f"error {result['file']}: {result['error']}", flush=True)
                    continue
                summaries.append(result["summary"])
                if result["trace"]:
                    traces[result["summary"]["file"]] = result["trace"]
    summaries.sort(key=lambda s: s.get("start") or "")
    write_json(SESSIONS_FILE, summaries)
    write_json(TRACES_FILE, traces)
    print(f"Dataset has {len(summaries)} session(s) and {len(traces)} trace(s). Errors: {errors}.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
