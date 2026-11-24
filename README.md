# EdgeWatcher

Distributed monitoring for IoT Edge devices over MQTT: content-based rules evaluated on each
device, alerts and a Node-RED dashboard. Student project for Distributed Systems (Master in IoT, UPM).

## Architecture

- **Device agent** (`agent/`, Python + psutil + Paho MQTT): runs on every device, publishes metrics
  and processes, evaluates its edge rules locally and publishes alerts (FIRING / RESOLVED).
- **Broker** (`mosquitto/`, Eclipse Mosquitto 2): all communication goes through it.
- **Central service** (`central/`, Python + FastAPI): history, rule management,
  alert de-duplication and forwarding to the dashboard. Split into 9 short modules
  (`config`, `state`, `storage`, `mqtt_client`, `handlers`, `rules`, `resend`, `api`, `central`).
- **Dashboard** (`nodered/`, Node-RED + FlowFuse Dashboard 2.0). 

## Run with Docker Compose

Requires Docker Desktop (or Docker Engine with Compose v2).

From the repository folder, on Windows, macOS or Linux:

```
docker compose up -d --build   # start
docker compose down            # stop
```

This starts the broker (port 1883), the central service (http://localhost:8000/docs),
Node-RED (http://localhost:1880, dashboard at http://localhost:1880/dashboard) and three simulated agents
(`sim-01` idle, `sim-02` busy, `sim-03` spiky). Watch their messages with the client included in
the broker container (nothing to install), or with MQTT Explorer:

```
docker compose exec mosquitto mosquitto_sub -v -t "devices/#"
```

Linux only: if Node-RED cannot write to `nodered/data`, run `sudo chown -R 1000:1000 nodered/data`.

### Inject load on a simulated agent

```
docker compose exec agent-2 touch /tmp/edgewatcher_load_sim-02   # CPU and RAM above 90 %
docker compose exec agent-2 rm /tmp/edgewatcher_load_sim-02      # back to normal
```

## Central service API

Used by Node-RED (`API_URL=http://central:8000`). Try every call from http://localhost:8000/docs.

| Method and path | Returns |
|---|---|
| `GET /devices` | `[{hostname, status}]`, sorted by hostname |
| `GET /devices/{h}/history` | Last hour, oldest first: `[{ts, cpu_percent, ram_percent, disk_percent}]` |
| `GET /devices/{h}/processes` | `{ts, top_cpu, top_ram}` (empty lists before the first report) |
| `GET /devices/{h}/rules` | `{version, rules}` (`{"version": 0, "rules": []}` if none) |
| `PUT /devices/{h}/rules` | Body `{"rules": [...]}` = the complete set. Returns `{version}`; 400 if `rules` is not a list |

An unknown hostname, or one with characters outside `A-Z a-z 0-9 . _ -`, returns 404. Each rule is
validated by the agent, which reports problems in its ACK (shown as the rule set's `error`).

The central service also publishes for Node-RED:

| Topic | QoS | Retained | Contents |
|---|---|---|---|
| `dashboard/{h}/state` | 0 | Yes | Status, OS, last metrics, active alerts, rules version and status (`applied` / `pending`) |
| `dashboard/alerts` | 1 | No | Each agent alert, unchanged, after de-duplication by `alert_id` |

Its data (history, `rules.json`, `active_alerts.json`) is kept in `data/`. To start from scratch:
`docker compose down -v`, delete everything in `data/` except `.gitkeep`, then `docker compose up -d --build`.

## Run the agent on a real device

On a Raspberry Pi or any Linux machine with a unique hostname (never the default `raspberrypi`):

```
git clone https://github.com/<user>/edgewatcher.git && cd edgewatcher
python3 -m venv .venv && source .venv/bin/activate
pip install -r agent/requirements.txt
python agent/agent.py --broker <broker-ip>
```

The full procedure (hostname, broker IP, firewall, running it as a service) is in the
Edge Device Quick Start below.

## Documentation

| Document | Contents |
|---|---|
| [`doc/00.EdgeWatcher_Requirements.docx`](doc/00.EdgeWatcher_Requirements.docx) | What to install on the broker laptop and on the edge device |
| [`doc/01.EdgeWatcher_Edge_Quick_Start.docx`](doc/01.EdgeWatcher_Edge_Quick_Start.docx) | Run the agent on a real device, step by step |
| [`doc/02.EdgeWatcher_Test_Guide.docx`](doc/02.EdgeWatcher_Test_Guide.docx) | 21 step-by-step tests of the agent, the infrastructure and the central service |

## Team

Frank · Eron · Iliya
