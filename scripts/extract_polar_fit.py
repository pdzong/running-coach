"""Download Polar Flow training sessions as FIT files.

Opens a browser window the first time and waits while you sign in. The login
stays in .polar-profile next to this project. The script never asks for your
password and does not store it.

Examples:
  py -3 scripts/download_polar_history.py
  py -3 scripts/update_polar.py
  py -3 scripts/extract_polar_fit.py --start 2023-01-01 --end 2023-12-31

After new files are saved, scripts/upload_polar_drive.py copies any FIT file
that is not already in the Google Drive folder. Pass --no-upload to skip that.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = ROOT / ".polar-profile"
DEFAULT_OUT = ROOT / "data" / "polar"
TRAINING_LIST_URL = "https://flow.polar.com/diary/training-list"
EXPORT_URL = "https://flow.polar.com/api/export/training/fit/{session_id}"

def say(message: str) -> None:
    print(message, flush=True)


def parse_iso_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use YYYY-MM-DD") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    span = parser.add_mutually_exclusive_group(required=True)
    span.add_argument(
        "--all",
        action="store_true",
        help="Every session Polar still lists, from the oldest through today",
    )
    span.add_argument(
        "--recent",
        action="store_true",
        help="Sessions from the last 31 days",
    )
    span.add_argument("--start", type=parse_iso_date, help="First day, YYYY-MM-DD")
    span.add_argument(
        "--last-days",
        type=int,
        help="How many days to include, ending today",
    )
    parser.add_argument("--end", type=parse_iso_date, help="Last day, YYYY-MM-DD. Default: today")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Folder for FIT files")
    parser.add_argument(
        "--login-timeout",
        type=int,
        default=300,
        help="Seconds to wait for you to sign in (default 300)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Hide the browser. Only works after a previous signed-in run",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List matching sessions and do not download them",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Do not copy new FIT files to Google Drive",
    )
    return parser


def resolve_span(args: argparse.Namespace) -> tuple[date, date, str]:
    today = date.today()
    if args.all:
        return date(2000, 1, 1), today, "all"
    if args.recent:
        return today - timedelta(days=30), today, "recent"
    if args.last_days is not None:
        if args.last_days < 1:
            raise SystemExit("--last-days must be at least 1")
        if args.end is not None:
            raise SystemExit("Use either --last-days or --end, not both")
        return today - timedelta(days=args.last_days - 1), today, "range"
    end = args.end or today
    if end < args.start:
        raise SystemExit("--end is before --start")
    return args.start, end, "range"


def browser_channel() -> str | None:
    candidates = {
        "chrome": [
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe",
        ],
        "msedge": [
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        ],
    }
    for channel, paths in candidates.items():
        if any(path.exists() for path in paths):
            return channel
    return None


def load_index(folder: Path) -> dict:
    path = folder / "index.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_index(folder: Path, index: dict) -> None:
    path = folder / "index.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def filename_from_disposition(disposition: str, session_id: str) -> str:
    match = re.search(r"filename\*=UTF-8''([^;]+)", disposition or "", flags=re.I)
    if match:
        name = unquote(match.group(1).strip())
    else:
        match = re.search(r'filename="([^"]+)"', disposition or "", flags=re.I)
        name = match.group(1) if match else f"{session_id}.FIT"
    name = Path(name).name
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    return name or f"{session_id}.FIT"


def dismiss_cookies(page) -> None:
    for label in ("Decline", "Allow all"):
        button = page.get_by_role("button", name=label)
        if button.count():
            try:
                button.first.click(timeout=1500)
            except Exception:
                return
            return


def training_list_ready(page) -> bool:
    if "auth.polar.com" in page.url or "/diary/training-list" not in page.url:
        return False
    return page.evaluate(
        """() => [...document.querySelectorAll('input.form-control')]
            .some((el) => /^\\d{2}\\/\\d{2}\\/\\d{4}$/.test(el.value))"""
    )


def wait_for_training_list(page, login_timeout_s: int, headless: bool) -> None:
    say("Opening Polar training history.")
    page.goto(TRAINING_LIST_URL, wait_until="domcontentloaded")
    dismiss_cookies(page)
    deadline = time.time() + login_timeout_s
    announced_login = False
    last_status = 0.0
    while time.time() < deadline:
        if "auth.polar.com" in page.url:
            if headless:
                raise SystemExit(
                    "Polar is not signed in. Run again without --headless and sign in in the browser window."
                )
            if not announced_login:
                say("Sign in in the browser window. The password stays there; this script does not read it.")
                announced_login = True
        elif "/diary/training-list" not in page.url:
            say("Signed in. Opening the training history list.")
            page.goto(TRAINING_LIST_URL, wait_until="domcontentloaded")
            dismiss_cookies(page)
        elif training_list_ready(page):
            say("Training history is open.")
            return
        elif time.time() - last_status > 5:
            say("Waiting for the training history dates to appear.")
            last_status = time.time()
        page.wait_for_timeout(500)
    raise SystemExit(
        "Timed out waiting for Polar Flow. Sign in in the browser window and run the command again."
    )


def collect_sessions(page, start: date, end: date, mode: str) -> list[dict]:
    """Ask Polar for the sessions in the date span.

    One history request returns the workouts that exist. It does not walk the
    calendar looking for months that contain training.
    """
    del mode  # The date span already distinguishes a full history from an update.
    say(f"Asking Polar for sessions from {start.isoformat()} through {end.isoformat()}.")
    result = page.evaluate(
        """async ({fromDate, toDate}) => {
            const headers = {
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'X-Requested-With': 'XMLHttpRequest',
            };
            const accountResponse = await fetch('/api/account/users/current/user', {
                credentials: 'include',
                headers,
            });
            if (!accountResponse.ok) return {status: accountResponse.status, rows: []};
            const account = await accountResponse.json();
            const userId = account.user && account.user.id;
            const response = await fetch('/api/training/history', {
                method: 'POST',
                credentials: 'include',
                headers: {...headers, 'Content-Type': 'application/json'},
                body: JSON.stringify({userId, fromDate, toDate}),
            });
            if (!response.ok) return {status: response.status, rows: []};
            const rows = await response.json();
            return {status: response.status, rows: Array.isArray(rows) ? rows : []};
        }""",
        {"fromDate": start.isoformat(), "toDate": end.isoformat()},
    )
    if result["status"] != 200:
        raise SystemExit(f"Polar history request failed with HTTP {result['status']}.")

    selected = []
    for row in result["rows"]:
        start_text = str(row.get("startDate") or "")
        if len(start_text) < 10:
            continue
        try:
            row_day = datetime.strptime(start_text[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if row_day < start or row_day > end:
            continue
        details = str(row.get("sportName") or "").strip()
        selected.append(
            {
                "id": str(row["id"]),
                "day": row_day,
                "text": f"{row_day.isoformat()} {details}".strip(),
            }
        )
    selected.sort(key=lambda row: (row["day"], row["id"]), reverse=True)
    if selected:
        say(
            f"Polar lists {len(selected)} session(s), "
            f"from {selected[-1]['day'].isoformat()} through {selected[0]['day'].isoformat()}."
        )
    return selected


def download_fit(context, session_id: str) -> tuple[str, bytes]:
    response = context.request.get(EXPORT_URL.format(session_id=session_id), timeout=60000)
    if not response.ok:
        raise RuntimeError(f"Polar returned HTTP {response.status}")
    body = response.body()
    if len(body) < 12 or body[8:12] != b".FIT":
        raise RuntimeError("response was not a FIT file; the Polar login may have expired")
    name = filename_from_disposition(response.headers.get("content-disposition", ""), session_id)
    return name, body


def copy_new_files_to_drive(folder: Path) -> None:
    script = Path(__file__).with_name("upload_polar_drive.py")
    if not script.exists():
        return
    say("Copying FIT files that are not in Google Drive yet.")
    completed = subprocess.run([sys.executable, str(script), "--dir", str(folder), "--if-authorized"])
    if completed.returncode not in (0, 2):
        say("Google Drive upload did not finish. The FIT files are still saved on this machine.")


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    args = build_parser().parse_args(argv)
    start, end, mode = resolve_span(args)
    out = args.out if args.out.is_absolute() else ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit(
            "Playwright is not installed. From the project folder run:\n"
            "  py -3 -m pip install -r requirements.txt"
        )

    channel = browser_channel()
    if mode == "all":
        say("Every session Polar has stored. Files already saved are skipped.")
    elif mode == "recent":
        say("Sessions from the last 31 days that are not saved yet.")
    else:
        say(f"Sessions from {start.isoformat()} through {end.isoformat()}.")
    say(f"Saving FIT files to {out}")

    with sync_playwright() as playwright:
        launch_kwargs = {
            "user_data_dir": str(PROFILE_DIR),
            "headless": args.headless,
            "viewport": {"width": 1280, "height": 900},
            "accept_downloads": True,
        }
        if channel:
            launch_kwargs["channel"] = channel
        context = playwright.chromium.launch_persistent_context(**launch_kwargs)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            try:
                wait_for_training_list(page, args.login_timeout, args.headless)
            except Exception as exc:
                if type(exc).__name__ == "TimeoutError":
                    raise SystemExit(
                        "Timed out waiting for Polar Flow. Sign in in the browser window and run the command again."
                    ) from exc
                raise
            sessions = collect_sessions(page, start, end, mode)
            say(f"Found {len(sessions)} completed session(s).")
            if args.dry_run:
                for session in sessions:
                    say(f"{session['day'].isoformat()}  {session['id']}  {session['text']}")
                return 0

            index = load_index(out)
            saved = skipped = 0
            failures: list[str] = []
            for session in sessions:
                session_id = session["id"]
                known = index.get(session_id)
                if known and (out / known["file"]).exists():
                    skipped += 1
                    say(f"skip {session['day'].isoformat()}  {known['file']}")
                    continue
                try:
                    name, body = download_fit(context, session_id)
                    (out / name).write_bytes(body)
                    index[session_id] = {
                        "date": session["day"].isoformat(),
                        "file": name,
                        "summary": session["text"],
                    }
                    save_index(out, index)
                    saved += 1
                    say(f"saved {session['day'].isoformat()}  {name}  ({len(body)} bytes)")
                except Exception as exc:
                    failures.append(f"{session['day'].isoformat()} {session_id}: {exc}")
                    say(f"failed {session['day'].isoformat()}  {session_id}: {exc}")
                time.sleep(0.2)
        finally:
            context.close()

    say(f"Saved {saved}, skipped {skipped}, failed {len(failures)}.")
    if saved and not args.no_upload:
        copy_new_files_to_drive(out)
    if failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
