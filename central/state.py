"""In-memory device state, rule tracking, and duplicate alert filter."""

import threading
from collections import deque
from config import SEEN_MAX

# Single lock shared across the MQTT thread, resend thread, and FastAPI HTTP thread
lock = threading.Lock()

devices = {}           # hostname -> live device state dictionary (Step 3)
rules = {}             # hostname -> {"version", "rules", "acked_version", "error"}
pending = {}           # hostname -> monotonic timestamp when rules were last sent
seen_ids = set()       # Set of processed alert_id strings for O(1) duplicate lookup
seen_order = deque(maxlen=SEEN_MAX)  # FIFO queue to evict oldest alert IDs


def ensure_device(h: str) -> dict:
    """Initialize and return the in-memory state dictionary for device h."""
    if h not in devices:
        devices[h] = {
            "status": "OFFLINE",
            "os": None,
            "simulated": None,
            "last_seen": None,
            "metrics": None,
            "processes": None,
            "active_alerts": {},  # Keyed by rule_id -> {rule_id, name, severity, since}
        }
    return devices[h]


def ensure_rules(h: str) -> dict:
    """Initialize and return the rule-tracking record for device h."""
    if h not in rules:
        rules[h] = {"version": 0, "rules": [], "acked_version": 0, "error": None}
    return rules[h]


def remember_alert(aid: str | None) -> bool:
    """Record alert_id; return False if missing or already seen (idempotency)."""
    if not aid or aid in seen_ids:
        return False
    if len(seen_order) == seen_order.maxlen:
        seen_ids.discard(seen_order[0])  # Drop oldest ID when capacity is reached
    seen_order.append(aid)
    seen_ids.add(aid)
    return True
