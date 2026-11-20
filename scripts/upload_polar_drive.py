"""Upload local Polar FIT files into a Google Drive folder.

The folder id is read from config/drive.json or the POLAR_DRIVE_FOLDER_ID
environment variable. That file is not committed. Sign in once in the browser
window; the script does not read or store the password. Later runs reuse
.google-profile and upload only files whose names are not already in the folder.

  py -3 scripts/upload_polar_drive.py
  py -3 scripts/upload_polar_drive.py --dry-run
  py -3 scripts/upload_polar_drive.py --headless

update_polar.py calls this after a download when the Google profile already
has a sign-in.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = ROOT / ".google-profile"
DEFAULT_DIR = ROOT / "data" / "polar"
DRIVE_CONFIG = ROOT / "config" / "drive.json"
ORIGIN = "https://drive.google.com"

def say(message: str) -> None:
    print(message, flush=True)


def folder_id_from_config() -> str:
    from_env = os.environ.get("POLAR_DRIVE_FOLDER_ID", "").strip()
    if from_env:
        return from_env
    if not DRIVE_CONFIG.exists():
        raise SystemExit(
            "Set POLAR_DRIVE_FOLDER_ID or create config/drive.json with "
            '{"folder_id": "<id from the Drive folder URL>"}.'
        )
    payload = json.loads(DRIVE_CONFIG.read_text(encoding="utf-8"))
    folder_id = str(payload.get("folder_id") or "").strip()
    if not folder_id:
        raise SystemExit("config/drive.json needs a folder_id.")
    return folder_id


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


def authorization_header(cookies: list[dict]) -> str:
    """Build the header Google accepts for a signed-in Drive page."""
    values = {cookie["name"]: cookie["value"] for cookie in cookies}
    sapisid = values.get("SAPISID")
    if not sapisid:
        raise PermissionError("Google session has no SAPISID cookie")
    timestamp = str(int(time.time()))
    parts = []
    names = (("SAPISIDHASH", "SAPISID"), ("SAPISID1PHASH", "__Secure-1PAPISID"), ("SAPISID3PHASH", "__Secure-3PAPISID"))
    for header_name, cookie_name in names:
        value = values.get(cookie_name)
        if not value:
            continue
        digest = hashlib.sha1(f"{timestamp} {value} {ORIGIN}".encode()).hexdigest()
        parts.append(f"{header_name} {timestamp}_{digest}")
    return " ".join(parts)


def drive_headers(context) -> dict[str, str]:
    return {
        "Authorization": authorization_header(context.cookies(ORIGIN)),
        "Origin": ORIGIN,
        "X-Origin": ORIGIN,
        "X-Goog-AuthUser": "0",
        "Referer": f"{ORIGIN}/",
    }


def wait_for_drive(page, folder_id: str, login_timeout_s: int, headless: bool) -> None:
    target = f"{ORIGIN}/drive/folders/{folder_id}"
    say("Opening the Google Drive folder.")
    page.goto(target, wait_until="domcontentloaded")
    deadline = time.time() + login_timeout_s
    announced = False
    while time.time() < deadline:
        url = page.url
        if "accounts.google.com" in url:
            if headless:
                raise SystemExit(
                    "Google Drive is not signed in. Run this command without --headless and sign in once."
                )
            if not announced:
                say("Sign in to Google in the browser window. The password stays there; this script does not read it.")
                announced = True
        elif folder_id in url and "drive.google.com" in url:
            say("Google Drive folder is open.")
            return
        page.wait_for_timeout(500)
    raise SystemExit("Timed out waiting for Google Drive. Sign in in the browser window and run the command again.")


def list_remote_names(context, folder_id: str) -> set[str]:
    names: set[str] = set()
    page_token = ""
    while True:
        params = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "fields": "nextPageToken,files(name)",
            "pageSize": "1000",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        if page_token:
            params["pageToken"] = page_token
        url = "https://www.googleapis.com/drive/v3/files?" + urlencode(params)
        response = context.request.get(url, headers=drive_headers(context), timeout=60000)
        if response.status == 401 or response.status == 403:
            body = response.text()[:300]
            raise PermissionError(f"Google Drive refused the file list (HTTP {response.status}). {body}")
        if not response.ok:
            raise RuntimeError(f"Google Drive file list failed with HTTP {response.status}: {response.text()[:300]}")
        payload = response.json()
        for item in payload.get("files") or []:
            name = item.get("name")
            if name:
                names.add(name)
        page_token = payload.get("nextPageToken") or ""
        if not page_token:
            return names


def upload_file(context, folder_id: str, path: Path) -> None:
    metadata = json.dumps({"name": path.name, "parents": [folder_id]}).encode("utf-8")
    start = context.request.post(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&supportsAllDrives=true",
        headers={
            **drive_headers(context),
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "application/octet-stream",
        },
        data=metadata,
        timeout=60000,
    )
    if not start.ok:
        raise RuntimeError(f"HTTP {start.status}: {start.text()[:300]}")
    location = start.headers.get("location")
    if not location:
        raise RuntimeError("Google Drive did not return an upload URL")
    body = path.read_bytes()
    uploaded = context.request.put(
        location,
        headers={"Content-Type": "application/octet-stream"},
        data=body,
        timeout=120000,
    )
    if not uploaded.ok:
        raise RuntimeError(f"HTTP {uploaded.status}: {uploaded.text()[:300]}")


def local_fit_files(folder: Path) -> list[Path]:
    if not folder.exists():
        raise SystemExit(f"No local Polar folder at {folder}")
    return sorted(path for path in folder.glob("*.FIT") if path.is_file())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="Folder of local FIT files")
    parser.add_argument("--dry-run", action="store_true", help="Show files that would be uploaded")
    parser.add_argument("--headless", action="store_true", help="Hide the browser. Only works after a previous sign-in")
    parser.add_argument(
        "--if-authorized",
        action="store_true",
        help="Exit quietly when Google has not been signed in yet",
    )
    parser.add_argument("--login-timeout", type=int, default=300, help="Seconds to wait for Google sign-in")
    return parser


def profile_has_login() -> bool:
    return (PROFILE_DIR / "Default" / "Network" / "Cookies").exists()


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    args = build_parser().parse_args(argv)
    folder = args.dir if args.dir.is_absolute() else ROOT / args.dir
    files = local_fit_files(folder)
    if args.if_authorized and not profile_has_login():
        say("Google Drive is not signed in yet, so new FIT files stayed on this machine.")
        say("Run: py -3 scripts/upload_polar_drive.py")
        return 2

    folder_id = folder_id_from_config()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("Playwright is not installed. From the project folder run:\n  py -3 -m pip install -r requirements.txt")

    channel = browser_channel()
    say(f"Checking {len(files)} local FIT file(s) against Google Drive.")
    with sync_playwright() as playwright:
        launch_kwargs = {
            "user_data_dir": str(PROFILE_DIR),
            "headless": args.headless or args.if_authorized,
            "viewport": {"width": 1280, "height": 900},
        }
        if channel:
            launch_kwargs["channel"] = channel
        context = playwright.chromium.launch_persistent_context(**launch_kwargs)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            wait_for_drive(page, folder_id, args.login_timeout, args.headless or args.if_authorized)
            try:
                remote_names = list_remote_names(context, folder_id)
            except PermissionError as exc:
                if args.if_authorized or args.headless:
                    say(f"Google Drive is not usable yet. {exc}")
                    say("Run: py -3 scripts/upload_polar_drive.py")
                    return 2
                raise SystemExit(str(exc)) from exc
            pending = [path for path in files if path.name not in remote_names]
            say(f"Drive already has {len(remote_names)} file(s). {len(pending)} local file(s) are new.")
            if args.dry_run:
                for path in pending:
                    say(f"would upload {path.name}")
                return 0
            uploaded = 0
            failed = 0
            for path in pending:
                try:
                    upload_file(context, folder_id, path)
                    uploaded += 1
                    say(f"uploaded {path.name}")
                except Exception as exc:
                    failed += 1
                    say(f"failed {path.name}: {exc}")
            say(f"Uploaded {uploaded}, already stored {len(files) - len(pending)}, failed {failed}.")
            return 1 if failed else 0
        finally:
            context.close()


if __name__ == "__main__":
    raise SystemExit(main())
