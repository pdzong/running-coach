"""Shared paths, athlete settings and formatting for the analysis scripts."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
POLAR_DIR = ROOT / "data" / "polar"
ANALYSIS_DIR = ROOT / "data" / "analysis"
DETAILS_DIR = POLAR_DIR / "details"
TARGETS_FILE = POLAR_DIR / "targets" / "targets.json"
ATHLETE_DIR = ROOT / "athlete"
PROFILE_FILE = ATHLETE_DIR / "profile.json"

RACE_DISTANCES = {"5k": 5000.0, "10k": 10000.0, "HM": 21097.5, "M": 42195.0}
# Polar's default zones as a share of max heart rate: zone 1 starts at 50%, zone 5 at 90%.
ZONE_FLOORS = (0.5, 0.6, 0.7, 0.8, 0.9)


def utf8_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def load_profile() -> dict:
    if not PROFILE_FILE.exists():
        raise SystemExit(
            f"Missing {PROFILE_FILE.relative_to(ROOT)}. Create it with "
            '{"hr_max": 190, "hr_rest": 50, "timezone": "Europe/Warsaw"}.'
        )
    profile = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
    profile.setdefault("timezone", "Europe/Warsaw")
    return profile


def local_zone(profile: dict) -> ZoneInfo:
    return ZoneInfo(profile["timezone"])


def zone_bounds(hr_max: int) -> list[tuple[int, int]]:
    floors = [round(f * hr_max) for f in ZONE_FLOORS] + [hr_max + 1]
    return [(floors[i], floors[i + 1] - 1) for i in range(5)]


def zone_of(hr: float, hr_max: int) -> int:
    """0 below zone 1, otherwise 1-5."""
    share = hr / hr_max
    zone = 0
    for index, floor in enumerate(ZONE_FLOORS):
        if share >= floor:
            zone = index + 1
    return zone


def trimp(hr_hist: dict, hr_max: int, hr_rest: int) -> float:
    """Banister TRIMP (male weighting) from a histogram of seconds per 5-bpm bucket."""
    total = 0.0
    for bucket, seconds in hr_hist.items():
        hr = int(bucket) + 2.5
        ratio = max(0.0, (hr - hr_rest) / (hr_max - hr_rest))
        total += seconds / 60 * ratio * 0.64 * 2.718281828 ** (1.92 * ratio)
    return total


def pace(speed_ms: float | None) -> str:
    if not speed_ms:
        return "-"
    seconds = 1000 / speed_ms
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def pace_from(seconds: float, km: float) -> str:
    per_km = seconds / km
    return f"{int(per_km // 60)}:{int(per_km % 60):02d}"


def clock(seconds: float) -> str:
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def load_json(path: Path, default=None):
    if not path.exists():
        if default is not None:
            return default
        raise SystemExit(f"Missing {path.relative_to(ROOT)}. Run: py -3 scripts/analysis/build_dataset.py")
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def is_run(session: dict) -> bool:
    return session.get("sport") == "running"
