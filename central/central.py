"""EdgeWatcher central service entry point (Step 1)."""

import argparse
import uvicorn
import handlers
import mqtt_client
import resend
import state
import storage
from api import app


def recover():
    """Restore persisted rule versions and open FIRING alerts from disk on startup."""
    storage.prepare()
    state.rules.update(storage.load_rules())
    for h, r in state.rules.items():
        state.ensure_device(h)
        if r.get("version", 0) > r.get("acked_version", 0):
            state.pending[h] = 0.0  # Mark unacknowledged rules for immediate resend
    for h, alerts in storage.load_active_alerts().items():
        state.ensure_device(h)["active_alerts"].update(alerts)


def main():
    """Parse CLI options, restore disk state, start MQTT + resend threads, and run API."""
    ap = argparse.ArgumentParser(description="EdgeWatcher central service")
    ap.add_argument("--broker", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--http-port", type=int, default=8000)
    args = ap.parse_args()

    recover()
    mqtt_client.start(args.broker, args.port, handlers.on_message)
    resend.start()
    uvicorn.run(app, host="0.0.0.0", port=args.http_port, log_level="warning")


if __name__ == "__main__":
    main()
