"""Stable storage: atomic JSON files and daily JSONL metric history."""

import json
import os
from datetime import datetime, timedelta, timezone
from config import ACTIVE_ALERTS_FILE, DATA, RULES_FILE


def prepare():
    """Ensure the base data directory exists on startup."""
    DATA.mkdir(parents=True, exist_ok=True)


def atomic_write(path, payload):
    """Write JSON to a temp file and atomically rename via os.replace (Step 1)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, path)


def load_rules() -> dict:
    """Load persisted rule sets and versions from data/rules.json."""
    return json.loads(RULES_FILE.read_text()) if RULES_FILE.exists() else {}


def save_rules(rules_data: dict):
    """Persist rule sets and ACK status atomically."""
    atomic_write(RULES_FILE, rules_data)


def load_active_alerts() -> dict:
    """Load open FIRING alerts from data/active_alerts.json on startup."""
    return json.loads(ACTIVE_ALERTS_FILE.read_text()) if ACTIVE_ALERTS_FILE.exists() else {}


def save_active_alerts(devices_data: dict):
    """Save active FIRING alerts per device so they survive a service restart."""
    snapshot = {h: d["active_alerts"] for h, d in devices_data.items() if d["active_alerts"]}
    atomic_write(ACTIVE_ALERTS_FILE, snapshot)


def append_metrics(h: str, payload: dict):
    """Append one JSON metric record to data/{hostname}/{YYYY-MM-DD}.jsonl."""
    ts = payload.get("ts") or datetime.now(timezone.utc).isoformat()
    folder = DATA / h
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / f"{ts[:10]}.jsonl", "a") as f:
        f.write(json.dumps(payload) + "\n")


def read_history(h: str, minutes: int = 60) -> list[dict]:
    """Read yesterday's and today's UTC JSONL files and return the last 60 minutes."""
    now = datetime.now(timezone.utc)
    since = (now - timedelta(minutes=minutes)).isoformat(timespec="seconds").replace("+00:00", "Z")
    out = []
    for offset in (1, 0):  # Yesterday first, then today so results are oldest-first
        day = (now - timedelta(days=offset)).date().isoformat()
        path = DATA / h / f"{day}.jsonl"
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            row = json.loads(line)
            if row.get("ts", "") >= since:
                out.append({k: row.get(k) for k in ("ts", "cpu_percent", "ram_percent", "disk_percent")})
    return out
