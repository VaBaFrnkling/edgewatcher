"""EdgeWatcher device agent.

Runs on every edge device. It:
  * publishes metrics every 5 s (QoS 0) and the top processes every 30 s (QoS 0);
  * evaluates its edge rules locally (content filtering at the source) and publishes an
    alert only when a rule changes state, FIRING or RESOLVED (QoS 1);
  * applies versioned rule sets received on a retained topic and acknowledges them (QoS 1);
  * reports ONLINE / OFFLINE on a retained status topic, with a Last Will;
  * keeps alerts in an in-memory buffer (up to 1000) while the broker is unreachable.

MQTT routes messages only by topic. Content-based filtering (selecting messages by the
values they contain) is built on top of it, here on the device, before publishing
(early filtering): only rule state changes leave the device as alerts.

Usage:
  python agent.py --broker <broker-ip>                          # real device (Raspberry Pi)
  python agent.py --broker <broker-ip> --simulate               # synthetic metrics
  python agent.py --simulate --hostname sim-01 --profile busy   # several simulated agents on one machine
"""
import argparse, json, os, platform, random, signal, socket, tempfile, threading, time, uuid
from collections import deque
from datetime import datetime, timezone

import psutil

RULE_METRICS = {"cpu_percent", "ram_percent", "disk_percent", "temp_c", "top_process_cpu"}
SEVERITIES = {"low", "medium", "high"}
OPS = {">": lambda a, b: a > b, ">=": lambda a, b: a >= b,
       "<": lambda a, b: a < b, "<=": lambda a, b: a <= b}
TOP_N = 15            # processes per list (top by CPU and top by RAM)
PROCESS_EVERY = 6     # publish the process lists every 6 samples (30 s with the default interval)
MB = 1024 * 1024


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# ---------------------------------------------------------------------------------------
# 1. Rule engine
# ---------------------------------------------------------------------------------------
def validate_rule(r):
    """Returns a clean copy of rule r, or raises ValueError saying what is wrong."""
    if not isinstance(r, dict):
        raise ValueError("each rule must be a JSON object")
    rid = r.get("rule_id")
    if not isinstance(rid, str) or not rid:
        raise ValueError("rule_id must be a non-empty string")
    if r.get("metric") not in RULE_METRICS:
        raise ValueError(f"{rid}: unknown metric {r.get('metric')!r}")
    if r.get("op") not in OPS:
        raise ValueError(f"{rid}: unknown operator {r.get('op')!r}")
    if not _is_number(r.get("threshold")):
        raise ValueError(f"{rid}: threshold must be a number")
    duration = r.get("duration_s", 0)
    if not _is_number(duration) or duration < 0:
        raise ValueError(f"{rid}: duration_s must be a number >= 0")
    severity = r.get("severity", "medium")
    if severity not in SEVERITIES:
        raise ValueError(f"{rid}: severity must be low, medium or high")
    enabled = r.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError(f"{rid}: enabled must be true or false")
    return {"rule_id": rid, "name": str(r.get("name") or rid)[:80], "metric": r["metric"],
            "op": r["op"], "threshold": r["threshold"], "duration_s": duration,
            "severity": severity, "enabled": enabled}


class RuleEngine:
    """Edge rules evaluated locally. Reports only state changes (FIRING / RESOLVED)."""

    def __init__(self, has_temp=True):
        self.has_temp = has_temp     # False if the device has no temperature sensor
        self.version = 0
        self.rules = []          # list of clean rule dicts
        self.state = {}          # rule_id -> {"state": "NORMAL"/"FIRING", "since": float|None}
        self.pending = []        # RESOLVED transitions caused by a new rule set
        self.lock = threading.Lock()

    def apply(self, rule_set):
        """Installs rule_set only if its version is higher.

        Returns (applied, error). Invalid rules are skipped and reported in error; the
        valid ones are still applied, so the central service is not stuck retrying.
        """
        if not isinstance(rule_set, dict):
            return False, "the rule set must be a JSON object"
        version = rule_set.get("version")
        if not isinstance(version, int) or isinstance(version, bool):
            return False, "version must be an integer"
        rules = rule_set.get("rules", [])
        if not isinstance(rules, list):
            return False, "rules must be a list"
        with self.lock:
            if version <= self.version:          # duplicate or old version: ignore
                return False, None
            new_rules, errors, seen = [], [], set()
            for r in rules:
                try:
                    clean = validate_rule(r)
                except ValueError as e:
                    errors.append(str(e))
                    continue
                if clean["metric"] == "temp_c" and not self.has_temp:
                    errors.append(f"{clean['rule_id']}: this device has no temperature sensor")
                    continue
                if clean["rule_id"] in seen:
                    errors.append(f"{clean['rule_id']}: duplicated rule_id")
                    continue
                seen.add(clean["rule_id"])
                new_rules.append(clean)
            old = {r["rule_id"]: r for r in self.rules}
            new = {r["rule_id"]: r for r in new_rules}
            # A rule keeps its state only if it is unchanged and still enabled. A rule that
            # was FIRING and is now removed, changed or paused is reported as RESOLVED.
            for rid in list(self.state):
                keep = rid in new and new[rid] == old.get(rid) and new[rid]["enabled"]
                if not keep:
                    if self.state[rid]["state"] == "FIRING":
                        self.pending.append(old[rid])
                    del self.state[rid]
            self.version = version
            self.rules = new_rules
            return True, "; ".join(errors) or None

    def evaluate(self, metrics, t):
        """Returns a list of (rule, new_state, value) transitions for one sample."""
        out = []
        with self.lock:
            for r in self.pending:
                out.append((r, "RESOLVED", metrics.get(r["metric"])))
            self.pending.clear()
            for r in self.rules:
                if not r["enabled"]:
                    continue
                value = metrics.get(r["metric"])
                if value is None:                 # e.g. no temperature sensor on this machine
                    continue
                st = self.state.setdefault(r["rule_id"], {"state": "NORMAL", "since": None})
                if OPS[r["op"]](value, r["threshold"]):
                    if st["since"] is None:
                        st["since"] = t
                    if st["state"] == "NORMAL" and t - st["since"] >= r["duration_s"]:
                        st["state"] = "FIRING"
                        out.append((r, "FIRING", value))
                else:
                    st["since"] = None
                    if st["state"] == "FIRING":
                        st["state"] = "NORMAL"
                        out.append((r, "RESOLVED", value))
        return out


# ---------------------------------------------------------------------------------------
# 2. Simulator
# ---------------------------------------------------------------------------------------
PROFILES = {
    "idle":  {"cpu": 15, "ram": 35, "noise": 3, "spikes": False},
    "busy":  {"cpu": 50, "ram": 65, "noise": 6, "spikes": False},
    "spiky": {"cpu": 30, "ram": 50, "noise": 4, "spikes": True},
}
SIM_OS = ["Raspberry Pi OS", "Ubuntu Server 24.04", "Debian 12"]
SIM_PROCESS_NAMES = ["python3", "node-red", "mosquitto", "nginx", "sensor-reader", "influxd",
                     "sshd", "systemd", "dockerd", "containerd", "cron", "rsyslogd",
                     "bluetoothd", "avahi-daemon", "NetworkManager", "dbus-daemon",
                     "camera-stream", "gpio-monitor", "telegraf", "bash"]


def clamp(v):
    return round(max(0.0, min(100.0, v)), 1)


class Simulator:
    """Synthetic metrics and processes, different for every hostname.

    The random generator is seeded with the hostname, so each simulated device has its own
    baseline and process list, and keeps them across restarts. The "spiky" profile adds
    short CPU spikes (5-20 s) that rules with a longer duration_s must ignore. While the
    load file exists, CPU and RAM climb above 90 % and one process takes most of the CPU.
    """

    def __init__(self, hostname, load_file, profile="idle", seed=None):
        self.rng = random.Random(seed if seed is not None else hostname)
        p = PROFILES[profile]
        self.load_file = load_file
        self.base_cpu = p["cpu"] + self.rng.uniform(-5, 5)
        self.base_ram = p["ram"] + self.rng.uniform(-8, 8)
        self.noise, self.spikes = p["noise"], p["spikes"]
        self.cpu, self.ram = self.base_cpu, self.base_ram
        self.disk = self.rng.uniform(30, 75)
        self.os_name = f"{self.rng.choice(SIM_OS)} (simulated)"
        self.total_ram_mb = self.rng.choice([1024, 2048, 4096, 8192])
        self.process_count = self.rng.randint(150, 240)
        self.spike_left = 0                  # samples left in the current spike
        self.cooldown = 0                    # samples before another spike may start
        self.procs = [{"pid": self.rng.randint(300, 30000), "name": n,
                       "weight": self.rng.uniform(0.2, 1.0),
                       "ram_mb": self.rng.uniform(5, 0.12 * self.total_ram_mb)}
                      for n in self.rng.sample(SIM_PROCESS_NAMES, 12)]
        self.procs[0]["weight"] = 3.0        # the device's main application

    def loaded(self):
        return os.path.exists(self.load_file)

    def read(self):
        """Returns (cpu_percent, ram_percent, disk_percent, temp_c)."""
        high = self.loaded()
        target_cpu, target_ram = (95.0, 92.0) if high else (self.base_cpu, self.base_ram)
        self.cooldown = max(0, self.cooldown - 1)
        if (self.spikes and not high and self.spike_left == 0 and self.cooldown == 0
                and self.rng.random() < 0.05):
            self.spike_left = self.rng.randint(1, 4)          # 1-4 samples = 5-20 s
            self.cooldown = self.spike_left + 6               # at least 30 s between spikes
        if self.spike_left > 0:
            self.spike_left -= 1
            self.cpu = self.rng.uniform(88, 99)
        else:
            self.cpu += (target_cpu - self.cpu) * 0.6 + self.rng.uniform(-self.noise, self.noise)
        self.ram += (target_ram - self.ram) * 0.3 + self.rng.uniform(-1, 1)
        self.disk = min(95.0, self.disk + self.rng.uniform(0, 0.01))
        self.process_count = max(80, self.process_count + self.rng.randint(-2, 2))
        self.cpu, self.ram = clamp(self.cpu), clamp(self.ram)
        temp = 38 + 0.35 * self.cpu + self.rng.uniform(-0.5, 0.5)
        return self.cpu, self.ram, round(self.disk, 1), round(temp, 1)

    def processes(self, cpu):
        """Synthetic process list consistent with the device's overall CPU."""
        weights = [p["weight"] * self.rng.uniform(0.7, 1.3) for p in self.procs]
        if self.loaded():
            weights[0] = sum(weights[1:]) * 20               # the main application hogs the CPU
        total, busy = sum(weights), cpu * 0.95
        out = []
        for p, w in zip(self.procs, weights):
            ram_mb = p["ram_mb"] * self.rng.uniform(0.95, 1.05)
            out.append({"pid": p["pid"], "name": p["name"],
                        "cpu_percent": round(busy * w / total, 1),
                        "ram_mb": round(ram_mb, 1),
                        "ram_percent": round(100 * ram_mb / self.total_ram_mb, 1)})
        return out


# ---------------------------------------------------------------------------------------
# 3. Real readings (psutil)
# ---------------------------------------------------------------------------------------
def read_os_name():
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return f"{platform.system()} {platform.release()}"


def read_temperature():
    """CPU temperature in degrees C, or None if the machine has no readable sensor."""
    try:
        temps = psutil.sensors_temperatures()       # Linux only (works on the Raspberry Pi)
    except (AttributeError, OSError):
        return None
    for key in ("cpu_thermal", "coretemp", "k10temp", "soc_thermal"):
        if temps.get(key):
            return round(temps[key][0].current, 1)
    for entries in temps.values():
        if entries:
            return round(entries[0].current, 1)
    return None


class ProcessScanner:
    """Reads the real process list.

    psutil needs two readings to compute a process's CPU use, so the constructor makes a
    first scan whose CPU figures are discarded. CPU is divided by the number of cores so
    that it is a share of the whole machine (0-100 %), like the overall cpu_percent.
    """

    def __init__(self):
        self.cores = psutil.cpu_count() or 1
        self.scan()

    def scan(self):
        out = []
        for p in psutil.process_iter(["pid", "name", "memory_info", "memory_percent"]):
            try:
                cpu = p.cpu_percent(None) / self.cores
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            mem = p.info.get("memory_info")
            out.append({"pid": p.info["pid"], "name": p.info["name"] or "?",
                        "cpu_percent": round(cpu, 1),
                        "ram_mb": round(mem.rss / MB, 1) if mem else 0.0,
                        "ram_percent": round(p.info.get("memory_percent") or 0, 1)})
        return out


def top_lists(procs):
    by_cpu = sorted(procs, key=lambda x: (x["cpu_percent"], x["ram_mb"]), reverse=True)[:TOP_N]
    by_ram = sorted(procs, key=lambda x: x["ram_mb"], reverse=True)[:TOP_N]
    return by_cpu, by_ram


# ---------------------------------------------------------------------------------------
# 4. MQTT and main loop
# ---------------------------------------------------------------------------------------
def parse_args(argv=None):
    p = argparse.ArgumentParser(description="EdgeWatcher device agent")
    p.add_argument("--broker", default="localhost")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--interval", type=float, default=5.0)
    p.add_argument("--keepalive", type=int, default=10)
    p.add_argument("--simulate", action="store_true")
    p.add_argument("--profile", choices=sorted(PROFILES), default="idle",
                   help="simulation only: idle, busy or spiky")
    p.add_argument("--load-file", default=None,
                   help="simulation only: while this file exists, high load is simulated")
    p.add_argument("--hostname", default=None,
                   help="override the hostname (only for running several simulated agents on one machine)")
    p.add_argument("--disk-path", default="/", help="partition whose usage is reported")
    return p.parse_args(argv)


def main(argv=None, stop=None):
    # Imported here so that the rule engine and the simulator can be imported without paho
    import paho.mqtt.client as mqtt

    a = parse_args(argv)
    host = a.hostname or socket.gethostname()
    if not host or any(c in host for c in "/+#"):
        raise SystemExit(f"Invalid hostname {host!r}: it is used in MQTT topics")
    base = f"devices/{host}"
    # New on every start: lets the central service tell a restart (rule states lost, so
    # FIRING alerts will never be RESOLVED) from a reconnection (states kept)
    boot_id = str(uuid.uuid4())
    load_file = a.load_file or os.path.join(tempfile.gettempdir(), f"edgewatcher_load_{host}")
    sim = Simulator(host, load_file, a.profile) if a.simulate else None
    engine = RuleEngine(has_temp=bool(sim) or read_temperature() is not None)
    scanner = None if sim else ProcessScanner()
    os_name = sim.os_name if sim else read_os_name()
    print(f"EdgeWatcher agent '{host}' ({os_name}) connecting to broker {a.broker}:{a.port}"
          + (f" (simulation, profile {a.profile}; create {load_file} to inject load)" if sim else ""),
          flush=True)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=host,
                         clean_session=True, protocol=mqtt.MQTTv311)
    client.will_set(f"{base}/status", json.dumps({"status": "OFFLINE", "hostname": host}),
                    qos=1, retain=True)
    client.reconnect_delay_set(min_delay=1, max_delay=10)
    unsent_alerts = deque(maxlen=1000)   # store-and-forward buffer while the broker is unreachable

    def on_connect(c, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"Connection refused: {reason_code}", flush=True)
            return
        print("Connected to the broker", flush=True)
        c.publish(f"{base}/status", json.dumps({"status": "ONLINE", "hostname": host, "boot_id": boot_id, "os": os_name,
                                                "simulated": bool(sim), "ts": now_iso()}),
                  qos=1, retain=True)
        c.subscribe(f"{base}/rules", qos=1)
        while unsent_alerts:                  # flush alerts detected while disconnected
            c.publish(f"{base}/alerts", unsent_alerts.popleft(), qos=1)

    def on_disconnect(c, userdata, flags, reason_code, properties):
        print(f"Disconnected from the broker ({reason_code}); retrying", flush=True)

    def on_message(c, userdata, msg):
        # An exception here would stop paho's network thread, so catch everything
        try:
            if msg.topic != f"{base}/rules" or not msg.payload:
                return                        # an empty message is a deleted retained rule set
            try:
                rule_set = json.loads(msg.payload)
            except ValueError:
                rule_set, applied, error = None, False, "the rule set is not valid JSON"
            else:
                applied, error = engine.apply(rule_set)
            if applied:
                print(f"Applied rule set version {engine.version}", flush=True)
            if error:
                print(f"Rule set problem: {error}", flush=True)
            # Always acknowledge the version we are running (even for duplicates),
            # otherwise the central service would keep republishing forever
            ack = {"version": engine.version, "applied": applied, "ts": now_iso()}
            if error:
                ack["error"] = error
            c.publish(f"{base}/rules/ack", json.dumps(ack), qos=1)
        except Exception as e:
            print(f"Error handling {msg.topic}: {e!r}", flush=True)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.connect_async(a.broker, a.port, keepalive=a.keepalive)  # keeps retrying if the broker is not up yet
    client.loop_start()

    stop = stop or threading.Event()
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        signal.signal(signal.SIGTERM, lambda *_: stop.set())   # docker stop

    last_net = psutil.net_io_counters()
    last_t = time.monotonic()
    psutil.cpu_percent(interval=None)        # starts the CPU measurement
    tick = 0
    while not stop.is_set():
        t = time.monotonic()
        if sim:
            cpu, ram, disk, temp = sim.read()
            procs = sim.processes(cpu)
            process_count = sim.process_count
        else:
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
            disk = psutil.disk_usage(a.disk_path).percent
            temp = read_temperature()
            procs = scanner.scan()
            process_count = len(procs)
        top = max(procs, key=lambda x: x["cpu_percent"]) if procs else None
        net = psutil.net_io_counters()
        dt = max(t - last_t, 1e-6)
        metrics = {"hostname": host, "ts": now_iso(), "os": os_name, "simulated": bool(sim),
                   "cpu_percent": cpu, "ram_percent": ram, "disk_percent": disk, "temp_c": temp,
                   "net_sent_kbps": round((net.bytes_sent - last_net.bytes_sent) * 8 / 1000 / dt, 1),
                   "net_recv_kbps": round((net.bytes_recv - last_net.bytes_recv) * 8 / 1000 / dt, 1),
                   "process_count": process_count,
                   "top_process_cpu": top["cpu_percent"] if top else None,
                   "top_process_name": top["name"] if top else None}
        last_net, last_t = net, t
        client.publish(f"{base}/metrics", json.dumps(metrics), qos=0)

        for rule, new_state, value in engine.evaluate(metrics, t):
            alert = {"alert_id": str(uuid.uuid4()), "hostname": host, "rule_id": rule["rule_id"],
                     "name": rule["name"], "state": new_state, "metric": rule["metric"],
                     "op": rule["op"], "value": value, "threshold": rule["threshold"],
                     "duration_s": rule["duration_s"], "severity": rule["severity"],
                     "rules_version": engine.version, "boot_id": boot_id, "ts": now_iso()}
            print(f"Alert {new_state}: {rule['name']} ({rule['metric']} = {value})", flush=True)
            if client.is_connected():
                client.publish(f"{base}/alerts", json.dumps(alert), qos=1)
            else:
                unsent_alerts.append(json.dumps(alert))

        if tick % PROCESS_EVERY == 0:
            by_cpu, by_ram = top_lists(procs)
            client.publish(f"{base}/processes",
                           json.dumps({"hostname": host, "ts": now_iso(), "process_count": process_count,
                                       "top_cpu": by_cpu, "top_ram": by_ram}), qos=0)
        tick += 1
        stop.wait(max(0.0, a.interval - (time.monotonic() - t)))

    # Clean shutdown: the broker discards the Last Will, so publish OFFLINE ourselves
    info = client.publish(f"{base}/status", json.dumps({"status": "OFFLINE", "hostname": host,
                                                        "ts": now_iso()}), qos=1, retain=True)
    try:
        info.wait_for_publish(timeout=3)
    except (RuntimeError, ValueError):
        pass                                  # not connected: the Last Will reports OFFLINE instead
    client.disconnect()
    client.loop_stop()
    print("Agent stopped", flush=True)


if __name__ == "__main__":
    main()
