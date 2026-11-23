# EdgeWatcher

Distributed monitoring for IoT Edge devices over MQTT: edge rules with alerts, content-based
subscriptions and a Node-RED dashboard. Student project for Distributed Systems (Master in IoT, UPM).

## Architecture

- **Device agent** (`agent/`, Python + psutil + Paho MQTT): runs on every device, publishes metrics
  and processes, evaluates its edge rules locally and publishes alerts (FIRING / RESOLVED).
- **Broker** (`mosquitto/`, Eclipse Mosquitto 2): all communication goes through it.
- **Central service** (`central/`, Python + FastAPI): history, rule management and
  content-based routing. *In progress.*
- **Dashboard** (`nodered/`, Node-RED + FlowFuse Dashboard 2.0). *In progress.*

## Run with Docker Compose

Requires Docker Desktop (or Docker Engine with Compose v2).

From the repository folder, on Windows, macOS or Linux:

```
docker compose up -d --build   # start
docker compose down            # stop
```

This starts the broker (port 1883), Node-RED (http://localhost:1880) and three simulated agents
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
| [`doc/02.EdgeWatcher_Test_Guide.docx`](doc/02.EdgeWatcher_Test_Guide.docx) | 18 step-by-step tests of the agent and the infrastructure |

## Team

Frank · Eron · Iliya
