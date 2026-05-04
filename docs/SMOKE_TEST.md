# Smoke Test

Manual verification, ~5 minutes. Run after any deploy or any significant code change. Designed to catch the regressions that automated tests miss — UI rendering, browser-specific WebSocket behavior, and end-to-end timing issues.

**Test environment assumption:** the FastAPI service is reachable at `${URL}` (substitute with the live URL or `http://localhost:5173` in local dev). Run through these steps in order.

## Steps

| # | Action | Expected result | If it fails |
|---|---|---|---|
| 1 | `curl -fsS ${URL}/health` | 200 response with `status: "healthy"` and `mqtt: "healthy"` and `database: "healthy"` in the `dependencies` block | Read the JSON — it tells you which dependency is degraded. Check `fly logs -a forge-broker` and `fly logs -a forge-dbs`. |
| 2 | `curl -fsS ${URL}/api/assets` | 200 response with a JSON array of 9 assets including `FSW-01`, `FSW-02`, `AFP-01`, `AFP-02`, `AUTO-01`, `CNC-01`, `CNC-02`, `CR-2CAT`, `HIF-CRANE` | If empty array, the simulator hasn't connected. Check `fly logs -a forge-sim`. |
| 3 | `curl -fsS ${URL}/api/oee` | 200 response with `total_assets: 9` and `online > 0` (after ~10 seconds of telemetry) | If `online: 0`, the broker → ingest path is broken. Check that both `forge-broker` and `forge-apis` are in the `started` state. |
| 4 | Open `${URL}` in Chrome (desktop, current version) | Factory floor SVG renders within 3 seconds; five area boxes labeled TANK FAB, COMPOSITES, CHEM PROC, 2CAT, HIF; nine machine dots distributed across them | If blank page, check browser console for asset-loading or JS errors. If areas render but no dots, the `/api/assets` call failed. |
| 5 | Wait 30 seconds | Most machine dots turn green (healthy). At least 7 of 9 should be green within 60 seconds. | If dots stay gray, telemetry isn't reaching the dashboard. Open browser devtools → Network → WS tab; the WebSocket should be open and receiving frames. |
| 6 | Click any green machine dot | Detail panel appears below the floor map. Title shows the machine name and ID; subtitle shows the type label and area/cell. | If no panel appears, the asset-click handler failed; check browser console. |
| 7 | Watch the metric cards in the detail panel for ~15 seconds | Each metric card shows a numeric current value, a redline range, and a live sparkline that grows leftward as new data arrives | If sparklines never appear, uPlot isn't getting buffer data; check the WS message stream in devtools. |
| 8 | Click "Fleet Overview" in the header | Table replaces the floor map; all 9 rows visible; STATUS column shows NOMINAL or ALARM per row | If table is empty, the same `/api/assets` issue as step 2. |
| 9 | Click "Factory Floor" in the header | Returns to the floor map view; previous selection cleared | If view doesn't switch, the React state update is broken. |
| 10 | Wait up to 5 minutes for the simulator's internal anomaly schedule to trigger an alarm (or proceed to step 11 to skip this) | One machine dot pulses red; an alarm appears in the right rail with the machine ID, the metric, and a redline-exceeded message; the alarm count badge increments | If no alarm appears in 5 minutes, the simulator's anomaly chance may need a kick; this is acceptable for the smoke test — proceed. |
| 11 | If an alarm is showing, click ACK on it | Button disappears; the alarm card dims; "ACKNOWLEDGED" text replaces the button | If button doesn't respond, the POST to `/api/alarms/{key}/ack` failed; check Network tab and `fly logs -a forge-apis`. |
| 12 | Wait for the simulator's anomaly to end (~30 seconds after raise) | The acknowledged alarm disappears from the active rail; the machine dot returns to green | If the alarm doesn't clear, the redline-recovery branch in `evaluate_alarm` isn't firing; check ingest logs. |
| 13 | Click "Alarm History" in the header | Table view shows the recently cleared alarm with its timestamp, asset, metric, value, and message | If empty, the alarm wasn't persisted to history (`alarm_history` deque or `alarms` table). |
| 14 | Open the same URL in a second browser tab | Factory floor renders identically; same machine states; alarms (if any) appear in both tabs simultaneously when raised | If second tab doesn't sync, the WebSocket fan-out is broken. Check `ws_clients` set behavior in `main.py`. |
| 15 | Close the second tab; in the first tab, kill the network briefly (devtools → Network → Offline → wait 10s → online) | "DISCONNECTED" indicator appears in the header during offline; reconnects within ~5 seconds when network returns; live data resumes | If the dashboard never recovers, the WebSocket reconnect logic in `App.jsx` is broken. |

## Pass criteria

The smoke test passes if steps 1–9 and step 14 all succeed. Steps 10–13 require a live anomaly which may not arrive in every 5-minute window; if they don't fire, exercise them manually via the `/faults` endpoint (queued for v.1.5) or skip with a note.

If any of steps 1–9 or 14 fail, the deploy is not considered live. Fix and re-run the full smoke test.

## Browser scope

Smoke test target: Chrome desktop, current version. Cross-browser support is out of scope for v.1 (`SPEC.md` §11.6). Firefox and Safari may render the SVG floor differently and have not been verified.

## Frequency

- Run after every deploy to a public URL.
- Run after any change to `main.py`, `simulator.py`, or `App.jsx`.
- Run before any external review of the system.
- Optional in pure-doc-change PRs.
