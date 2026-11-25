# Node-RED implementation and verification

Updated on 25 November 2026 against the running Central Service, Node-RED 4.0.9, and FlowFuse Dashboard 1.37.0.

Evidence is distinguished below: automated checks run during the review, Docker tests run by Iliya with terminal output or dashboard confirmation, and a teammate's fresh-clone test.

## Implemented

All four pages share one visual style: cards, colour labels for status and severity, and the same colours and buttons.

- Fleet: one card per device, built by a single template, so sim-01, sim-02, sim-03 and any new hostname get the same layout automatically. Each card shows ONLINE/OFFLINE status, OS, temperature, last update, active alerts, CPU/RAM/disk gauges (green below 60%, orange 60–80%, red from 80%) and a 10-minute live chart. Offline devices are greyed out. A summary at the top counts devices, online, offline and active alerts. Live state comes from the retained dashboard/+/state topic.
- Alerts: dashboard/alerts at QoS 1, persistent MQTT session, newest-first events, notifications, a 500-event display, and 10000 recent duplicate IDs. The table has All / Firing / Resolved filters with counts, a search box and pagination (25, 50, 100… up to 500 rows per page). An atomic snapshot in /data/alerts-cache.json restores the display and duplicate filter after a fresh consumer starts.
- Device: GET /devices, latest CPU/RAM/disk values, last-hour CPU/RAM/disk history chart, and top-CPU and top-RAM process tables. Responses from older selections are ignored; replies retain the requesting browser identity.
- Rules: complete-set GET/PUT, validated drafts, enable/disable switch, removal, version and ACK status, device errors, stale-save protection, and one in-flight dashboard save per device. Draft discard uses inline confirmation.

## Checks performed

The 24 November verification recorded 19 executable source/component checks, 9 live backend/MQTT integration checks and 3 recovery checks: 31 passing checks. These are not the separate Annex C checklist. On 25 November the 19 component checks and the repository smoke script passed again.

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
| Additional-device handler and card rendering | PASS on the earlier Fleet layout: generic handler tests and a controlled rendering check with existing simulator data |
| Independent Device browser selections | PASS: sim-02 and sim-01 remained separate |
| Stale rule save rejected | PASS: browser showed reload warning; lock and version checks also tested |
| API unavailable and restored | PASS: visible ECONNREFUSED, then history loaded after restoring configuration and reopening |
| Test cleanup | PASS: original sim-01 rule list restored; no load flags created; no permanent fake devices created |

## Container integration checks completed

These Docker operations were run by Iliya. They supplement the earlier component and MQTT-disconnect tests rather than changing their original count.

| Check | Result and evidence |
|---|---|
| Fresh Docker build and smoke test | PASS, user-reported terminal output. A teammate also reported a successful fresh clone, local merge, image build and four-page dashboard test on 24 November. |
| Node-RED restart and saved alerts | PASS, user-reported restart and dashboard confirmation that saved events remained. |
| Alerts while Node-RED was stopped | PASS, user-reported delivery of FIRING and RESOLVED after restart. |
| Alerts while Central was stopped | PASS, user-reported delivery of FIRING and RESOLVED after restart. |
| Agent pause / Last Will / recovery | PASS, user-reported OFFLINE after pause and ONLINE after unpause. |
| Broker outage and agent alert buffer | PASS, user confirmed the guided 25 November test: broker stopped, simulated load applied to sim-02, then broker restored and load removed; FIRING and RESOLVED appeared. Full broker-outage terminal logs were not supplied. |
| Rule retransmission while awaiting ACK | PASS, supplied terminal transcript on 25 November. sim-03 version 3 was published at 01:39:23 UTC and retried at 01:39:34. After OFFLINE at 01:39:37 there were no further rule publications before ONLINE at 01:41:09. An applied ACK for version 3 then arrived. Later applied:false ACKs indicate duplicate rule deliveries were ignored. |
| Agent restart clears an open alert | PASS, supplied before/after MQTT state on 25 November. At 01:44:08 UTC sim-02 had one High CPU alert, CPU 97.4%, and version 1 acknowledged. After restart and load removal, the 01:45:14 state was ONLINE, CPU 58.5%, active_alerts empty, and version 1 still acknowledged/applied with no error. |

The sim-03 retry test resaved its existing empty rule set (version 2 to 3); it created no extra device. The restart test removed its simulated load flag. Alert history remains as test evidence.

## Dashboard redesign (25 November)

The four pages were restyled after the checks above. The data flow, MQTT topics, HTTP calls, validation and save logic are unchanged, except on the Fleet page: the 48 fixed nodes for sim-01/02/03 (functions, gauges, texts, charts) and their three groups were replaced by one template, and the device-discovery function now handles every hostname instead of skipping the three simulators. Gauges and charts are now drawn by the template instead of the ui-gauge and ui-chart nodes.

On the Alerts page, the saved-event count is shown in the table header, so the third output of the deduplication function (the old count text) is no longer connected.

| Check after the redesign | Result |
|---|---|
| flows.json is valid JSON, with unique IDs, no broken wires and no widgets pointing to deleted groups | PASS |
| Each page compared against a static preview with sample data | PASS |
| Alerts page in the running dashboard | PASS: card, filters, search and pagination displayed |
| Fleet, Device and Rules pages with live data | To be confirmed in the running dashboard |

## Resolved backend finding

The 25 November audit reproduced a duplicate-ACK issue in Central's `central/handlers.py`, `_handle_ack`. Replaying an identical `applied:true` ACK for an already acknowledged version cleared the device's active alerts, because it was treated as an agent restart.

This is fixed in commit 505bbfa. `_handle_ack` now remembers the last ACK and ignores an identical copy, while a new ACK for the same version (a real restart) still clears the active alerts. An isolated run of the actual handler confirmed both cases: the restart ACK cleared the alerts, and a repeated identical ACK left one active alert in place. The repository does not include an automated regression test for this case.

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
- Every device, including new hostnames, gets the same Fleet card automatically; no flow changes are needed when a device connects.
- History/processes are fetched on selection and Refresh, rather than continuously polled.
- The Fleet chart shows the last 10 minutes of live samples kept in Node-RED memory. It restarts empty with the flow; durable historical samples remain in the Central Service.
- Alert cache is bounded to the latest 500 events and 10000 IDs; it is a dashboard recovery cache, not an unlimited audit log.
- If writing the alert cache fails, the warning appears in the Node-RED debug panel and log, not on the Alerts page.
- Save locking coordinates dashboard clients. The backend has no atomic conditional-PUT endpoint, so simultaneous edits from external tools cannot be fully serialized by Node-RED.
- No authentication/TLS is added; this remains the local course demo described by the project.
- Test runs incremented sim-01's version counter while restoring its original rule list. QA-labelled FIRING/RESOLVED events remain as test evidence in the saved Alerts list.

## Repository notes

Only `flows.json`, `package.json` and `settings.js` from `nodered/data` are tracked. The alert cache, runtime configuration, backups, `node_modules` and the collected monitoring data in `data/` are excluded by `.gitignore`.
