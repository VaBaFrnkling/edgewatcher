"""Background daemon thread that republishes unacknowledged rules (Step 11)."""

import threading
import time
import state
from config import ACK_TIMEOUT_S, RESEND_POLL_S
from mqtt_client import publish_rules


def _loop():
    """Every 2 s, republish pending rules older than 10 s if device is ONLINE."""
    while True:
        time.sleep(RESEND_POLL_S)
        with state.lock:
            for h, sent_at in list(state.pending.items()):
                is_online = state.devices.get(h, {}).get("status") == "ONLINE"
                if time.monotonic() - sent_at > ACK_TIMEOUT_S and is_online:
                    publish_rules(h)


def start():
    """Start the rule-republish background thread."""
    threading.Thread(target=_loop, daemon=True).start()
