# Node RED implementation and verification

Verified on 24 November 2026 against the running Central Service, Node-RED 4.0.9, and FlowFuse Dashboard 1.37.0.

## Implemented

- Fleet: retained live state, three simulator cards with gauges and charts, automatic cards for additional hostnames, and ONLINE/OFFLINE presentation.
- Alerts: dashboard/alerts at QoS 1, persistent MQTT session, newest-first searchable events, notifications, a 500-event display, and 10000 recent duplicate IDs. An atomic snapshot in /data/alerts-cache.json restores the display and duplicate filter after a fresh consumer starts.
- Device: GET /devices, last-hour CPU/RAM/disk history, and top-CPU and top-RAM process tables. Responses from older selections are ignored; replies retain the requesting browser identity.
- Rules: complete-set GET/PUT, validated drafts, enable/disable, removal, version and ACK status, device errors, stale-save protection, and one in-flight dashboard save per device. Draft discard uses inline confirmation.

## Checks performed

19 executable source/component checks passed, plus 9 live backend/MQTT integration checks and 3 recovery checks. These are 31 passing checks, not the teammate's separate Annex C checklist.

| Check | Result |
|---|---|
| Function syntax, Vue compilation, unique IDs, complete wiring | PASS |
| Three real simulator states and retained startup delivery | PASS |
| All devices: chronological history, process shapes, versioned rules | PASS |
| Sustained condition produces FIRING after its duration | PASS |
| Rule ACK, disable, RESOLVED, newest-first ordering | PASS |
| Invalid agent rule reports an ACK error | PASS |
| Real alert replay twice, including after reconnect | PASS: no duplicate rows |
| Disk snapshot and restore into a fresh Function context | PASS |
| Events produced during an MQTT disconnect | PASS: FIRING and RESOLVED delivered on reconnect |
| Additional-device handler and card rendering | PASS: generic handler tests and a controlled rendering check with existing simulator data |
| Independent Device browser selections | PASS: sim-02 and sim-01 remained separate |
| Stale rule save rejected | PASS: browser showed reload warning; lock and version checks also tested |
| API unavailable and restored | PASS: visible ECONNREFUSED, then history loaded after restoring configuration and reopening |
| Test cleanup | PASS: original sim-01 rule list restored; no load flags created; no permanent fake devices created |

## Release checks that have not run

- Full Docker container/process restart, agent stop/pause/LWT, and broker container restart: blocked by Docker socket permissions. A real MQTT disconnect and fresh Function context were tested instead; these do not replace a process/container restart.
- Fresh Docker image build: blocked by Docker permissions. The accompanying Dockerfile/Compose change is prepared but not built in this session.
- Real Raspberry Pi, cross-laptop/hotspot, and the teammate's exact ten-step Annex C checklist: require the hardware/network or a supplied checklist. The repository currently contains an 18-test agent/infrastructure guide, not a separate ten-step Annex C document.
- Mobile viewport: the test browser remained at a fixed 1280 CSS pixels; a true mobile viewport was not verified.

## Run and verify

From the repository root after applying the setup patch:

```sh
docker compose up -d --build
docker compose exec -T nodered node < nodered/tests/smoke.cjs
docker compose restart nodered
docker compose ps
```

Open http://localhost:1880/dashboard/fleet and /alerts, /device, /rules. After the restart, saved alerts should still display, retained state should return, history should load, and existing saved rules should remain. Do not use down -v for normal verification.

The smoke script runs read-only HTTP/flow checks; it does not claim to exercise browser interactions or Docker failure scenarios.

## Operation and limits

- Node-RED connects to mosquitto:1883. The HTTP base is API_URL, normally http://central:8000 inside Docker.
- New devices are displayed under Additional devices; known simulator cards preserve the original layout.
- History/processes are fetched on selection and Refresh, rather than continuously polled.
- Live Fleet chart data restarts with the flow; durable historical samples remain in the Central Service.
- Alert cache is bounded to the latest 500 events and 10000 IDs; it is a dashboard recovery cache, not an unlimited audit log. Do not commit it.
- Save locking coordinates dashboard clients. The backend has no atomic conditional-PUT endpoint, so simultaneous edits from external tools cannot be fully serialized by Node-RED.
- No authentication/TLS is added; this remains the local course demo described by the project.
- Test runs incremented sim-01's version counter while restoring its original rule list. QA-labelled FIRING/RESOLVED events remain as test evidence in the saved Alerts list.

## Git handoff

Commit flows.json, package.json, Dockerfile, .dockerignore, docker-compose.yml, this guide, and the smoke test. Keep node_modules, alert cache, runtime credentials/configuration, and collected monitoring data out of Git.
