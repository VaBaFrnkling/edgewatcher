"""Persistent MQTT client (clean_session=False) and Annex A.1 publishers."""

import json
import time
import paho.mqtt.client as mqtt
import state
from config import CLIENT_ID, KEEPALIVE_S, SUBSCRIPTIONS

# Persistent session ensures Mosquitto queues QoS 1 alerts while central is down
client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
    client_id=CLIENT_ID,
    clean_session=False,
    protocol=mqtt.MQTTv311,
)


def build_state(h: str) -> dict:
    """Format device state to match the exact Annex A.1 nested JSON contract."""
    d = state.ensure_device(h)
    r = state.ensure_rules(h)
    rule_status = "applied" if r["acked_version"] >= r["version"] else "pending"
    return {
        "hostname": h,
        "status": d["status"],
        "os": d["os"],
        "simulated": d["simulated"],
        "last_seen": d["last_seen"],
        "metrics": d["metrics"],
        "active_alerts": list(d["active_alerts"].values()),
        "rules": {
            "version": r["version"],
            "acked_version": r["acked_version"],
            "status": rule_status,
            "error": r["error"],
        },
    }


def publish_state(h: str):
    """Publish nested device state for Node-RED (QoS 0, retained)."""
    client.publish(f"dashboard/{h}/state", json.dumps(build_state(h)), qos=0, retain=True)


def publish_alert(raw_or_dict):
    """Forward deduplicated alert to Node-RED (QoS 1, not retained)."""
    payload = raw_or_dict if isinstance(raw_or_dict, str) else json.dumps(raw_or_dict)
    client.publish("dashboard/alerts", payload, qos=1, retain=False)


def publish_rules(h: str):
    """Publish versioned rule set to agent (QoS 1, retained) and start ACK timer."""
    r = state.ensure_rules(h)
    body = json.dumps({"version": r["version"], "rules": r["rules"]})
    client.publish(f"devices/{h}/rules", body, qos=1, retain=True)
    state.pending[h] = time.monotonic()


def on_connect(c, userdata, flags, reason_code, properties):
    """Re-subscribe to all 5 device wildcard topics on every connection."""
    if not reason_code.is_failure:
        c.subscribe(SUBSCRIPTIONS)


def start(broker: str, port: int, on_message):
    """Connect asynchronously and start Paho's background network thread."""
    client.on_connect = on_connect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=10)
    client.connect_async(broker, port, keepalive=KEEPALIVE_S)
    client.loop_start()
