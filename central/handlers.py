"""Handlers for incoming MQTT messages from device agents (Steps 4 to 9)."""

import json
import state
import storage
from config import METRIC_KEYS, valid_host
from mqtt_client import publish_alert, publish_state


def _handle_metrics(h: str, d: dict, p: dict):
    """Store latest metrics, mark device ONLINE, and append to daily JSONL."""
    d["metrics"] = {k: p.get(k) for k in METRIC_KEYS}
    d["last_seen"] = p.get("ts")
    d["status"] = "ONLINE"
    if p.get("os") is not None:
        d["os"] = p["os"]
    if "simulated" in p:
        d["simulated"] = p["simulated"]
    storage.append_metrics(h, p)


def _handle_status(d: dict, p: dict):
    """Update ONLINE/OFFLINE status from agent connect, clean exit, or Last Will."""
    d["status"] = p.get("status", "OFFLINE")
    if p.get("os") is not None:
        d["os"] = p["os"]
    if "simulated" in p:
        d["simulated"] = p["simulated"]


def _handle_alert(h: str, d: dict, p: dict, raw_text: str) -> bool:
    """Deduplicate by alert_id, update active_alerts.json, and forward to Node-RED."""
    if not state.remember_alert(p.get("alert_id")):
        return False
    rid = p.get("rule_id")
    if p.get("state") == "FIRING" and rid:
        d["active_alerts"][rid] = {
            "rule_id": rid, "name": p.get("name"),
            "severity": p.get("severity"), "since": p.get("ts"),
        }
    elif p.get("state") == "RESOLVED" and rid:
        d["active_alerts"].pop(rid, None)
    storage.save_active_alerts(state.devices)
    publish_alert(raw_text)
    return True


def _handle_ack(h: str, d: dict, p: dict):
    """Process rule ACK, detect agent restarts, and clear pending timer (Step 9)."""
    r = state.ensure_rules(h)
    key = json.dumps(p, sort_keys=True)  # A QoS 1 duplicate is an identical copy of the ACK
    if key == r.get("last_ack"):
        return  # The same ACK delivered twice: not a restart, nothing to do
    r["last_ack"] = key
    ver = int(p.get("version", 0))
    applied = p.get("applied")
    if applied is True and ver == r["acked_version"] and ver > 0:
        d["active_alerts"].clear()  # Agent restarted and lost its local alert state
        storage.save_active_alerts(state.devices)
    if ver > r["version"]:
        r["version"], r["acked_version"] = ver, ver
        r["error"] = "rules changed outside the central service"
    else:
        r["acked_version"] = ver
        if applied is not False or p.get("error") is not None:
            r["error"] = p.get("error")  # Keep prior error on duplicate reconnect ACK
    if r["acked_version"] >= r["version"]:
        state.pending.pop(h, None)
    storage.save_rules(state.rules)


def on_message(c, userdata, msg):
    """Route devices/{hostname}/{kind} messages inside try/except (Step 2)."""
    try:
        if not msg.payload:  # Ignore cleared retained messages
            return
        parts = msg.topic.split("/")
        if len(parts) < 3 or parts[0] != "devices" or not valid_host(parts[1]):
            return
        h, kind = parts[1], "/".join(parts[2:])
        raw_text = msg.payload.decode("utf-8")
        p = json.loads(raw_text)
        with state.lock:
            d = state.ensure_device(h)
            if kind == "processes":
                d["processes"] = {"ts": p.get("ts"), "top_cpu": p.get("top_cpu", []), "top_ram": p.get("top_ram", [])}
                return  # Processes stay in memory only; nothing published (Step 5)
            if kind == "metrics":
                _handle_metrics(h, d, p)
            elif kind == "status":
                _handle_status(d, p)
            elif kind == "alerts" and not _handle_alert(h, d, p, raw_text):
                return
            elif kind == "rules/ack":
                _handle_ack(h, d, p)
            publish_state(h)
    except Exception as e:
        print(f"Error handling {msg.topic}: {e!r}", flush=True)