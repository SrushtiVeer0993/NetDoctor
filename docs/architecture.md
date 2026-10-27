# NetDoctor — Architecture

## Pipeline

    MEASURE → ANALYZE → IDENTIFY PROBABLE PROBLEM → RECOMMEND → MONITOR RESULT

Every diagnostic run keeps these four kinds of output distinct, both in the
API response and in the UI:

- **Measured facts** — `gateway`, `internet`, `latency`, `packet_loss`, `dns`, `websites`
- **Rule-based interpretation** — `findings[].evidence`
- **Probable diagnosis** — `findings[].text`, with `severity` and `confidence`
- **Recommendations** — `recommendations[]`

The diagnosis engine (`app/services/legacy_diagnostics.py::diagnose`) is
explicitly rule-based and is never called "AI" anywhere in the code, UI
copy, or docs. The same applies to anomaly detection (`app/services/anomaly.py`)
— it's always labeled "Anomaly Detection", including the optional
Isolation Forest pass.

## Gateway vs. Internet logic

`check_gateway_connectivity()` sets `icmp_unavailable: true` whenever the
gateway doesn't answer ICMP. `diagnose()` only escalates to "possible local
connectivity problem" when **both** gateway and internet are unreachable.
A silent gateway with working internet is reported as an informational
finding ("gateway may be filtering ICMP"), not a local-network failure —
this matters for mobile hotspots, carrier NAT, VPNs and firewalled routers.

## HTTP status handling

`test_websites()` records `status_code` and a separate `successful_request`
boolean (`status_code < 400`). A 403/404/5xx still counts as `reachable`.
The diagnosis engine and the frontend both use this distinction rather than
treating every non-200 as "site down".

## DEMO MODE

`app/services/demo_data.py` is the only place allowed to invent results.
Every demo function returns `"simulated": true`, and every endpoint that
can go through demo mode accepts an optional `?demo=` query param (falls
back to the user's saved `Settings.demo_mode` — see `api/deps.resolve_demo_mode`).
Simulated and real results are never mixed in one response; the frontend
renders a "Demo mode — simulated" badge (`components/DemoBadge.tsx`)
wherever `simulated: true` comes back.

## Backend layout

    backend/app/
      core/        settings, JWT + bcrypt password hashing
      db/          SQLAlchemy engine/session, declarative Base
      models/      users, diagnostic_runs, network_devices, speed_tests,
                   traceroute_runs/hops, monitoring_sessions/measurements,
                   alert_rules/alert_events, reports, user_settings
      schemas/     Pydantic request/response models
      api/         one router per feature area (see table below)
      services/    business logic — one module per feature, OS-specific
                   commands go through network/interface.py instead of
                   living here
      network/     OS abstraction seam: interface.py is the ONLY module the
                   rest of the app imports from; windows.py / linux.py /
                   macos.py hold the actual subprocess calls

| Area | Router | Service(s) |
|---|---|---|
| Auth | `api/auth.py` | `core/security.py` |
| Dashboard | `api/dashboard.py` | reads `DiagnosticRun` |
| Diagnostics | `api/diagnostics.py` | `services/legacy_diagnostics.py` (ported from the original Flask app) |
| Network (interfaces/traceroute/connections/map/discover) | `api/network.py` | `network/interface.py`, `services/legacy_diagnostics.discover_local_devices` |
| Speed Test | `api/speedtest.py` | `services/speedtest.py` |
| Live Monitoring | `api/monitoring.py` (REST + `/ws/monitor` WebSocket) | `services/alerts.py` |
| Alerts | `api/alerts.py` | fired from the monitoring WebSocket loop |
| Packet Analyzer | `api/packets.py` | `services/packet_capture.py` (Scapy) |
| Analytics / Anomaly Detection | `api/analytics.py` | `services/analytics.py`, `services/anomaly.py` |
| Reports | `api/reports.py` | `services/reports.py` (ReportLab/CSV/JSON) |
| Settings | `api/settings.py` | `models/settings.py` |

`legacy_diagnostics.py` is the original NetDoctor `diagnostics.py`, ported
function-for-function onto the new backend, plus the ICMP/HTTP-status
nuances above.

## WebSocket auth

Browsers cannot attach custom headers to a WebSocket handshake, so
`/ws/monitor` takes the JWT as a query parameter (`?token=`) rather than
the `Authorization` header the REST endpoints use. The token is decoded
with the same `decode_access_token()` as everywhere else.

## Alerting

Alerts are evaluated live inside the `/ws/monitor` loop
(`services/alerts.ConsecutiveTracker`) against the user's `Settings`
thresholds. A rule fires exactly once per breach episode — when the
consecutive-breach count first reaches the configured threshold — and
resets once the metric recovers, so a single noisy sample never triggers
a false alarm and a sustained problem doesn't spam duplicate alerts.

## Packet capture

`services/packet_capture.py` wraps `scapy.AsyncSniffer` in a background
thread, started/stopped via REST rather than blocking a request. Captures
live in an in-process dict (`_captures`) plus a JSON snapshot under
`$TMPDIR/netdoctor_captures/` — per spec section 23, raw captures never go
into PostgreSQL, only metadata would. This is a single-process design
(fine for a course project / one backend instance); a production version
would move capture state to Redis or a dedicated worker.

Requires root/administrator privileges and, in Docker, the `NET_RAW` /
`NET_ADMIN` capabilities already set in `docker-compose.yml`. Without them,
`start_capture()` returns `{"supported": false, "error": "..."}` — the API
and frontend both surface this as "Unavailable on this system" rather than
fabricating packets (unless DEMO MODE is on).

## Anomaly detection

`services/anomaly.py` implements the trailing-window z-score approach
first (mean/std over the last 5 data points, flag `|z| >= 2.5`), matching
the spec's required order. `isolation_forest_anomalies()` is a secondary,
optional multivariate pass over `[latency, packet_loss, dns]` — it
requires at least 10 historical runs and returns `None` (not an error)
otherwise.

## What's simplified vs. the original spec

- `latency_measurements`, `packet_loss_measurements`, `dns_measurements`,
  `http_tests` are not separate tables — they're stored as the `result_json`
  JSON column on `diagnostic_runs`, plus flattened columns
  (`latency_avg_ms`, `packet_loss_pct`, `dns_response_ms`) for cheap
  analytics queries. This keeps one diagnostic run's full detail queryable
  as a unit (used directly by the PDF/CSV/JSON report generator) without a
  four-table join.
- Packet captures are process-local (see above) rather than a distributed
  store.
- `alert_rules` exists as a table for future per-metric custom rules, but
  Phase 5's actual alerting reads thresholds straight from `user_settings`
  (latency/packet-loss/consecutive-checks) rather than per-rule rows — the
  simpler path matches what the Settings page actually exposes.
