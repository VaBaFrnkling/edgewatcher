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
- **Dashboard** (`nodered/`, Node-RED + FlowFuse Dashboard 2.0): four pages (Fleet, Alerts,
  Device and Rules) that read live state over MQTT and query the central service over HTTP.

## Run with Docker Compose

Requires Docker Desktop (or Docker Engine with Compose v2).

From the repository folder, on Windows, macOS or Linux:

```
docker compose up -d --build   # start
docker compose down            # stop
```

This starts:

- the broker on port 1883;
- the central service, with its API docs at http://localhost:8000/docs;
- Node-RED at http://localhost:1880, with the dashboard at http://localhost:1880/dashboard/fleet;
- three simulated agents: `sim-01` (idle), `sim-02` (busy) and `sim-03` (spiky).

Watch their messages with the client included in the broker container (nothing to install),
or with MQTT Explorer:

```
docker compose exec mosquitto mosquitto_sub -v -t "devices/#"
```

Linux only: if Node-RED cannot write to `nodered/data`, run `sudo chown -R 1000:1000 nodered/data`.

### Inject load on a simulated agent

```
docker compose exec agent-2 touch /tmp/edgewatcher_load_sim-02   # CPU and RAM above 90 %
docker compose exec agent-2 rm /tmp/edgewatcher_load_sim-02      # back to normal
```

## Node-RED dashboard

Open http://localhost:1880/dashboard/fleet. The other pages are in the navigation menu.

| Page | Contents |
|---|---|
| Fleet | One card per device (new devices appear automatically): status, temperature, last update, active alerts, CPU/RAM/disk gauges and a 10-minute live chart |
| Alerts | Saved FIRING and RESOLVED events, newest first, with a state filter, search and pagination (latest 500) |
| Device | Last hour of CPU, RAM and disk for the selected device, plus its top 15 processes by CPU and by RAM |
| Rules | View, add, enable/disable and remove a device's rules, then save the complete set and follow its acknowledgement |

The custom Node-RED image installs FlowFuse Dashboard automatically. The flows and the alert
recovery cache are kept in `nodered/data` (bind mount). See
[Node-RED operation and verification](doc/NodeRED_Verification.md).

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

Its data (history, `rules.json`, `active_alerts.json`) is kept in `data/`.

To start from scratch:

1. Run `docker compose down -v`.
2. Delete everything in `data/` except `.gitkeep`, and delete `nodered/data/alerts-cache.json`
   (the saved Alerts list).
3. Run `docker compose up -d --build`.

## Run the agent on a real device

On a Raspberry Pi or any Linux machine with a unique hostname (never the default `raspberrypi`):

```
git clone https://github.com/VaBaFrnkling/edgewatcher.git && cd edgewatcher
python3 -m venv .venv && source .venv/bin/activate
pip install -r agent/requirements.txt
python agent/agent.py --broker <broker-ip>
```

The full procedure (hostname, broker IP, firewall, running it as a service) is in the
Edge Device Quick Start, listed under Documentation.

## Documentation

| Document | Contents |
|---|---|
| [`doc/EdgeWatcher.docx`](doc/EdgeWatcher.docx) | Project report |
| [`doc/00.EdgeWatcher_Requirements.docx`](doc/00.EdgeWatcher_Requirements.docx) | What to install on the broker laptop and on the edge device |
| [`doc/01.EdgeWatcher_Edge_Quick_Start.docx`](doc/01.EdgeWatcher_Edge_Quick_Start.docx) | Run the agent on a real device, step by step |
| [`doc/02.EdgeWatcher_Test_Guide.docx`](doc/02.EdgeWatcher_Test_Guide.docx) | 21 step-by-step tests of the agent, the infrastructure and the central service |
| [`doc/NodeRED_Verification.md`](doc/NodeRED_Verification.md) | How the Node-RED dashboard works and how it was verified |

## Team

Frank · Eron · Iliya
