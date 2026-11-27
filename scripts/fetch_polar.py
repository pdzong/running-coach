"""Save Polar Flow session details and planned training targets.

details: per-session analysis (coach target, phase results, laps, notes) for
recent sessions in data/polar/index.json that have no saved details yet.
targets: planned targets from the Polar calendar, including the ones synced from
TrainingPeaks, merged into data/polar/targets/targets.json.

Uses the sign-in in .polar-profile. If it has expired, run
py -3 scripts/update_polar.py and sign in in the browser window.

  py -3 scripts/fetch_polar.py details
  py -3 scripts/fetch_polar.py details --days 90
  py -3 scripts/fetch_polar.py targets
  py -3 scripts/fetch_polar.py targets --start 2026-12-01 --end 2027-01-31
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta

from extract_polar_fit import PROFILE_DIR, ROOT, TRAINING_LIST_URL, browser_channel, say

POLAR_DIR = ROOT / "data" / "polar"
DETAILS_DIR = POLAR_DIR / "details"
TARGETS_FILE = POLAR_DIR / "targets" / "targets.json"

HEADERS_JS = "{'Accept': 'application/json, text/javascript, */*; q=0.01', 'X-Requested-With': 'XMLHttpRequest'}"

DETAILS_JS = """async (sid) => {
    const h = %s;
    const out = {};
    for (const part of ['summary', 'details']) {
        const r = await fetch(`/api/training/analysis/${sid}/${part}`, {credentials: 'include', headers: h});
        out[part] = r.ok ? await r.json() : {status: r.status};
    }
    return out;
}""" % HEADERS_JS

CALENDAR_JS = """async ({start, end}) => {
    const h = %s;
    const r = await fetch(`/training/getCalendarEvents?start=${start}&end=${end}`, {credentials: 'include', headers: h});
    if (!r.ok) return {status: r.status};
    const events = (await r.json()).filter((e) => e.type === 'TRAININGTARGET');
    const targets = {};
    for (const e of events) {
        const id = e.ListItemId || e.listItemId;
        const t = await fetch(`/api/trainingtarget/${id}`, {credentials: 'include', headers: h});
        targets[id] = t.ok ? await t.json() : {status: t.status};
    }
    return {events, targets};
}""" % HEADERS_JS


def event_id(event: dict) -> str:
    return str(event.get("ListItemId") or event.get("listItemId"))


def parse_day(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def open_polar(playwright):
    kwargs = {"user_data_dir": str(PROFILE_DIR), "headless": True}
    channel = browser_channel()
    if channel:
        kwargs["channel"] = channel
    context = playwright.chromium.launch_persistent_context(**kwargs)
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(TRAINING_LIST_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    if "auth.polar.com" in page.url:
        context.close()
        raise SystemExit("Polar is not signed in. Run py -3 scripts/update_polar.py and sign in in the browser window.")
    return context, page


def fetch_details(page, days: int, refresh: bool) -> None:
    index = json.loads((POLAR_DIR / "index.json").read_text(encoding="utf-8"))
    since = (date.today() - timedelta(days=days)).isoformat()
    DETAILS_DIR.mkdir(parents=True, exist_ok=True)
    wanted = [sid for sid, entry in index.items() if entry.get("date", "") >= since
              and (refresh or not (DETAILS_DIR / f"{sid}.json").exists())]
    say(f"Fetching details for {len(wanted)} session(s) since {since}.")
    for sid in sorted(wanted, key=lambda s: index[s]["date"]):
        data = page.evaluate(DETAILS_JS, sid)
        if "status" in data.get("summary", {}):
            say(f"failed {index[sid]['date']} {sid}: HTTP {data['summary']['status']}")
            continue
        (DETAILS_DIR / f"{sid}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        say(f"saved {index[sid]['date']} {sid}")


def fetch_targets(page, start: date, end: date) -> None:
    events, targets = [], {}
    day = start
    while day <= end:
        stop = min(day + timedelta(days=6), end)
        result = page.evaluate(CALENDAR_JS, {"start": day.strftime("%d.%m.%Y"), "end": stop.strftime("%d.%m.%Y")})
        if "status" in result:
            raise SystemExit(f"Polar calendar request failed for {day}: HTTP {result['status']}")
        events += result["events"]
        targets.update(result["targets"])
        day = stop + timedelta(days=1)

    saved = {"events": [], "targets": {}}
    if TARGETS_FILE.exists():
        saved = json.loads(TARGETS_FILE.read_text(encoding="utf-8"))
    # Polar drops a target from the calendar once a session completes it, so past targets are kept.
    fetched_ids = {event_id(e) for e in events}
    today = date.today().isoformat()
    kept = [
        e for e in saved["events"]
        if event_id(e) not in fetched_ids
        and not (max(start.isoformat(), today) <= e["datetime"][:10] <= end.isoformat())
    ]
    saved["events"] = sorted(kept + events, key=lambda e: e["datetime"])
    saved["targets"].update({str(k): v for k, v in targets.items()})
    saved["fetched"] = datetime.now().isoformat(timespec="minutes")
    TARGETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TARGETS_FILE.write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"Saved {len(events)} planned target(s) from {start} to {end} into {TARGETS_FILE.relative_to(ROOT)}.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("details", help="Session details for recent sessions")
    p.add_argument("--days", type=int, default=31, help="How far back to look (default 31)")
    p.add_argument("--refresh", action="store_true", help="Fetch again even when saved")
    p = sub.add_parser("targets", help="Planned targets from the Polar calendar")
    p.add_argument("--start", type=parse_day, default=date.today() - timedelta(days=14))
    p.add_argument("--end", type=parse_day, default=date.today() + timedelta(days=42))
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        context, page = open_polar(playwright)
        try:
            if args.command == "details":
                fetch_details(page, args.days, args.refresh)
            else:
                fetch_targets(page, args.start, args.end)
        finally:
            context.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
