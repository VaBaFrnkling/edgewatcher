"""FastAPI HTTP endpoints for Node-RED queries and rule updates (Annex A.2)."""

from fastapi import Body, FastAPI, HTTPException
import rules
import state
import storage
from config import valid_host

app = FastAPI(title="EdgeWatcher Central Service")


def _require_device(h: str) -> dict:
    """Validate hostname safety and return 404 if device is unknown (Step 12)."""
    if not valid_host(h) or h not in state.devices:
        raise HTTPException(status_code=404, detail="Unknown or invalid hostname")
    return state.devices[h]


@app.get("/devices")
def get_devices():
    """Return sorted list of [{hostname, status}] for all known devices."""
    with state.lock:
        return [{"hostname": h, "status": state.devices[h]["status"]} for h in sorted(state.devices)]


@app.get("/devices/{h}/history")
def get_history(h: str):
    """Return last 60 minutes of CPU, RAM, and disk metrics oldest-first."""
    with state.lock:
        _require_device(h)
    return storage.read_history(h, minutes=60)


@app.get("/devices/{h}/processes")
def get_processes(h: str):
    """Return latest top_cpu and top_ram process lists (or empty defaults)."""
    with state.lock:
        d = _require_device(h)
        return d["processes"] or {"ts": None, "top_cpu": [], "top_ram": []}


@app.get("/devices/{h}/rules")
def get_rules(h: str):
    """Return current rule version and rule list for device h."""
    with state.lock:
        _require_device(h)
        r = state.rules.get(h)
        return {"version": r["version"], "rules": r["rules"]} if r else {"version": 0, "rules": []}


@app.put("/devices/{h}/rules")
def put_rules(h: str, body: dict = Body(...)):
    """Replace complete rule set for device h; return 400 if rules is not a list."""
    with state.lock:
        _require_device(h)
    if not isinstance(body.get("rules"), list):
        raise HTTPException(status_code=400, detail="'rules' must be a list")
    return {"version": rules.update_rules(h, body["rules"])}
