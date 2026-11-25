# Node-RED implementation and verification

Updated on 25 November 2026 against the running Central Service, Node-RED 4.0.9, and FlowFuse Dashboard 1.37.0.

Evidence is distinguished below: automated checks run during the review, Docker tests run by Iliya with terminal output or dashboard confirmation, and the teammate's fresh-clone test. The review environment cannot access the Docker socket directly.

## Implemented

- Fleet: retained live state, three simulator cards with gauges and charts, automatic cards for additional hostnames, and ONLINE/OFFLINE presentation.
- Alerts: dashboard/alerts at QoS 1, persistent MQTT session, newest-first searchable events, notifications, a 500-event display, and 10000 recent duplicate IDs. An atomic snapshot in /data/alerts-cache.json restores the display and duplicate filter after a fresh consumer starts.
- Device: GET /devices, last-hour CPU/RAM/disk history, and top-CPU and top-RAM process tables. Responses from older selections are ignored; replies retain the requesting browser identity.
- Rules: complete-set GET/PUT, validated drafts, enable/disable, removal, version and ACK status, device errors, stale-save protection, and one in-flight dashboard save per device. Draft discard uses inline confirmation.

## Checks performed

The 24 November verification recorded 19 executable source/component checks, 9 live backend/MQTT integration checks and 3 recovery checks: 31 passing checks. These are not the teammate's separate Annex C checklist. On 25 November the 19 component checks and the repository smoke script passed again.

The 25 November review also confirmed that all three devices were ONLINE, the saved flows matched the running flows, and agent rule-engine checks passed for sustained conditions, single transitions, duplicate rule versions, disabling, invalid metrics and top-15 process sorting. A 1,000-sample run of the actual sim-03 simulator and rule engine contained 95 CPU samples above 80% and no FIRING event for the 30-second sustained rule.

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

## Container integration checks completed

These Docker operations were run by Iliya. They supplement the earlier component and MQTT-disconnect tests rather than changing their original count.

| Check | Result and evidence |
|---|---|
| Fresh Docker build and smoke test | PASS, user-reported terminal output. The teammate also reported a successful fresh clone, local merge, image build and four-page dashboard test on 24 November. |
| Node-RED restart and saved alerts | PASS, user-reported restart and dashboard confirmation that saved events remained. |
| Alerts while Node-RED was stopped | PASS, user-reported delivery of FIRING and RESOLVED after restart. |
| Alerts while Central was stopped | PASS, user-reported delivery of FIRING and RESOLVED after restart. |
| Agent pause / Last Will / recovery | PASS, user-reported OFFLINE after pause and ONLINE after unpause. |
| Broker outage and agent alert buffer | PASS, user confirmed the guided 25 November test: broker stopped, simulated load applied to sim-02, then broker restored and load removed; FIRING and RESOLVED appeared. Full broker-outage terminal logs were not supplied. |
| Rule retransmission while awaiting ACK | PASS, supplied terminal transcript on 25 November. sim-03 version 3 was published at 01:39:23 UTC and retried at 01:39:34. After OFFLINE at 01:39:37 there were no further rule publications before ONLINE at 01:41:09. An applied ACK for version 3 then arrived. Later applied:false ACKs indicate duplicate rule deliveries were ignored. |
| Agent restart clears an open alert | PASS, supplied before/after MQTT state on 25 November. At 01:44:08 UTC sim-02 had one High CPU alert, CPU 97.4%, and version 1 acknowledged. After restart and load removal, the 01:45:14 state was ONLINE, CPU 58.5%, active_alerts empty, and version 1 still acknowledged/applied with no error. |

The sim-03 retry test resaved its existing empty rule set (version 2 to 3); it created no extra device. The restart test removed its simulated load flag. Alert history remains as test evidence.

## Open backend finding

The 25 November audit reproduced a duplicate-ACK issue in Central's `central/handlers.py`, `_handle_ack`. Replaying an identical `applied:true` ACK for an already acknowledged version clears the device's active alerts, because it is treated as an agent restart. In an isolated test of the actual handler, one active alert became zero without a RESOLVED event.

This finding remains open until a fix and regression test are supplied. Normal restart recovery passing does not establish that duplicate successful ACKs are harmless. The fix must preserve restart recovery while making duplicate ACK delivery idempotent.

## Verification still outside this sign-off

- The repository contains a 21-test agent/infrastructure/central guide. This report does not claim that every test in that guide, or every step of the separate ten-step Annex C checklist, has been executed.
- Real Raspberry Pi and cross-laptop/hotspot tests have not been verified here. The team's agreed presentation uses sim-01, sim-02 and sim-03. Any mandatory hardware criterion must be checked against the original course brief.
- A true mobile viewport has not been verified.
- The lecturer's original marking brief is not available for a complete criterion-by-criterion grading check.

## Run and verify

From the repository root:

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

## Git and submission handoff

The completed dashboard was merged into main in commit 55526b0. Commit this updated verification report with the final test results. Keep node_modules, alert cache, runtime credentials/configuration, and collected monitoring data out of Git.

The separate four-page `EdgeWatcher_NodeRED_Flow_Documentation.pdf` has been completed and sent to the team. Include it in the submission ZIP alongside the final team report PDF, presentation and source code. The verification report is not a substitute for the flow documentation. Confirm the team report's four-page limit and the author spelling (Ilya/Iliya) in the final exported PDF.
