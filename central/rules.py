"""Versioned rule-set updates triggered by PUT /devices/{h}/rules (Step 8)."""

import state
import storage
from mqtt_client import publish_rules, publish_state


def update_rules(h: str, new_rules: list) -> int:
    """Increment version, persist rules.json, publish retained QoS 1, and mark pending."""
    with state.lock:
        state.ensure_device(h)
        r = state.ensure_rules(h)
        r["version"] += 1
        r["rules"] = new_rules
        r["error"] = None
        storage.save_rules(state.rules)
        publish_rules(h)
        publish_state(h)
        return r["version"]
