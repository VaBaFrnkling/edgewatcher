"""Configuration constants, MQTT subscriptions, and hostname validation."""

import os
import re
from pathlib import Path

# Storage paths (EW_DATA is /data inside Docker Compose, ./data locally)
DATA = Path(os.environ.get("EW_DATA", "./data"))
RULES_FILE = DATA / "rules.json"
ACTIVE_ALERTS_FILE = DATA / "active_alerts.json"

# MQTT session and timing parameters (Step 2 & Step 11 of Central Service Guide)
CLIENT_ID = "edgewatcher-central"
KEEPALIVE_S = 30
ACK_TIMEOUT_S = 10   # Republish unacknowledged rules after 10 seconds
RESEND_POLL_S = 2    # Background resend thread check interval
SEEN_MAX = 5000      # Maximum alert_id UUIDs kept in duplicate filter

# Allowed hostname characters to prevent path traversal in data/{hostname}/
HOST_RE = re.compile(r"^[A-Za-z0-9._-]+$")

# Wildcard subscriptions (never subscribe to # or our own devices/+/rules topic)
SUBSCRIPTIONS = [
    ("devices/+/metrics", 0),    # At-most-once telemetry (every 5 s)
    ("devices/+/processes", 0),  # At-most-once top processes (every 30 s)
    ("devices/+/alerts", 1),     # At-least-once state-change alerts
    ("devices/+/rules/ack", 1),  # At-least-once rule acknowledgements
    ("devices/+/status", 1),     # At-least-once ONLINE/OFFLINE and Last Will
]


def valid_host(h: str) -> bool:
    """Return True only if hostname is safe to use as a directory name."""
    return bool(HOST_RE.match(h)) and ".." not in h
