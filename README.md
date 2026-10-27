# NetDoctor

**Network Diagnostics, Monitoring & Analysis Platform**

A "doctor for your network": measure â†’ analyze â†’ identify probable
problem â†’ recommend â†’ monitor result. Built as a B.Tech Computer Networks
course project.

All 14 pages from the spec are implemented: Landing, Login/Register,
Dashboard, Diagnostics, Speed Test, Live Monitor, Network Map, Traceroute,
Connections, Packet Analyzer, Analytics, Alerts, Reports, Settings â€” backed
by a FastAPI + PostgreSQL backend with JWT auth, a rule-based diagnosis
engine, statistical anomaly detection, and PDF/CSV/JSON report export.

## Problem statement

Most people troubleshoot a "slow internet" complaint by guessing. NetDoctor
instead runs a structured set of measurements (gateway, internet, latency,
packet loss, DNS, HTTP) and applies transparent, rule-based logic to
suggest a *probable* cause â€” never a certainty â€” along with concrete next
steps, plus live monitoring, historical analytics, and exportable reports.

## Objectives

- Demonstrate core Computer Networks concepts through real, working code
  (not just UI copy) â€” see `docs/networking-concepts.md`.
- Clearly separate measured facts, rule-based interpretation, probable
  diagnosis, and recommendations at every layer (API response, database,
  UI).
- Avoid common false-positives: an ICMP-silent gateway or a non-200 HTTP
  response is never treated as an outright failure; a missing traceroute
  hop is never assumed to be packet loss.
- Never fabricate a measurement â€” everything that can't be performed on
  the current system (permissions, unsupported OS, no libpcap, etc.)
  returns "Unavailable on this system" instead of fake data, unless DEMO
  MODE is explicitly on (see below).

## Features

| Page | What it does |
|---|---|
| Dashboard | Network status overview, health score, recent diagnosis, recent tests |
| Diagnostics | Full measure â†’ analyze â†’ diagnose â†’ recommend pipeline |
| Speed Test | Download/upload throughput with labeled methodology |
| Live Monitor | WebSocket-streamed latency/packet-loss/DNS + live chart + in-line alerts |
| Network Map | ARP-based LAN topology, local subnet only |
| Traceroute | Hop-by-hop path visualization |
| Connections | Active TCP/UDP sockets with state filters |
| Packet Analyzer | Scapy-based capture, protocol breakdown, click-to-inspect |
| Analytics | Historical trends (today/7d/30d), stats, period comparison |
| Alerts | Fired after N consecutive threshold breaches (not on one noisy sample) |
| Reports | PDF/CSV/JSON export of any past diagnostic run |
| Settings | Default targets, alert thresholds, DEMO MODE toggle |

## Tech stack

- **Frontend:** React, Vite, TypeScript, Tailwind CSS, React Router, Axios, Recharts, Lucide icons
- **Backend:** FastAPI, Pydantic, SQLAlchemy, Alembic
- **Database:** PostgreSQL
- **Auth:** JWT + bcrypt with SHA-256 prehashing for long passwords; legacy bcrypt hashes upgrade on successful login
- **Networking:** OS ping/ARP/traceroute/netstat via `subprocess`, DNS via `socket`, HTTP via `requests`, packets via `scapy`
- **Analytics:** NumPy, Pandas, scikit-learn (optional Isolation Forest)
- **Reports:** ReportLab (PDF), csv/json (stdlib)
- **DevOps:** Docker, Docker Compose

## Installation

### Option A â€” Docker Compose (recommended)

```bash
cp .env.example .env      # set SECRET_KEY and POSTGRES_PASSWORD
docker compose up --build
```

- Backend: http://localhost:8000 (docs at `/docs`)
- Frontend: http://localhost:5173
- Postgres: localhost:5433 (container port 5432)

Packet capture and raw ICMP need elevated privileges â€” `docker-compose.yml`
already grants the backend container `NET_RAW`/`NET_ADMIN`. On a host where
these are still blocked, use DEMO MODE (Settings page) instead of fighting
the platform.

#### Windows host diagnostics

Docker Desktop's backend container sees a virtual Linux interface and Docker
gateway, not the Windows Wi-Fi/Ethernet adapter. On Windows, start NetDoctor
from PowerShell with the project launcher. It creates a private host-agent
token in `.env` when needed, starts the Compose services, and runs diagnostics
on the Windows host so gateway results refer to the active physical adapter:

```powershell
Set-Location 'C:\path\to\netdoctor'
powershell -ExecutionPolicy Bypass -File .\start-netdoctor.ps1
```

Keep that PowerShell window open while using NetDoctor. If the host agent is
not running, diagnostics will show a warning that results come from the Docker
container rather than silently treating its bridge gateway as the Wi-Fi router.

The agent binds port 8765 and requires the bearer token. Permit inbound traffic
only from Docker Desktop's private virtual network in Windows Firewall if
needed; do not create a Public-profile or unrestricted LAN rule. The agent has
only fixed `diagnostics`, `interface`, `discovery`, and `speedtest` operations;
it does not accept shell commands. If it is stopped, diagnostics and speed
tests identify container-side results instead of presenting them as laptop
measurements. A configured but unavailable agent causes the speed-test request
to fail with an explanation. ARP neighbor discovery is a partial view of
devices the host has recently seen, not a complete network inventory.

### Option B â€” run locally

**Backend**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# set DATABASE_URL to a running Postgres instance, or use sqlite:///./netdoctor.db for a quick local run
# With the Compose database: postgresql+psycopg2://netdoctor:netdoctor@localhost:5433/netdoctor
uvicorn app.main:app --reload
```

Packet capture (`scapy`) needs `libpcap` on the host and root/admin
privileges for the process â€” install `libpcap-dev` (Linux) or run as
Administrator (Windows) if you want real captures; otherwise the Packet
Analyzer page will report "Unavailable on this system", or use DEMO MODE.

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

## Environment variables

See `.env.example`. Key ones:

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | JWT signing key â€” change before any real use |
| `DATABASE_URL` | SQLAlchemy connection string |
| `CORS_ORIGINS` | Comma-separated origins the API accepts requests from |
| `DEMO_MODE` | Server-wide default; per-user override lives in Settings / `user_settings.demo_mode` |
| `VITE_API_BASE_URL` | Backend URL the frontend calls (REST and WebSocket) |

## Database setup

`docker compose up` runs Postgres automatically. Two Alembic migrations
exist:

```bash
cd backend
alembic upgrade head
```

- - `0001_initial` â€” users, diagnostic_runs
- `0002_phase_3_9_tables` â€” network_devices, speed_tests, traceroute_runs/hops,
  monitoring_sessions/measurements, alert_rules/alert_events, reports, user_settings
- `0003_monitoring_source` â€” simulated/live flags for monitoring records
- `0004_nullable_connectivity` â€” preserves unavailable gateway/connectivity states
- `0005_monitoring_source` â€” labels measurement runtime and preserves inconclusive monitoring connectivity

`Base.metadata.create_all()` also runs on backend startup as a fast-start
fallback after Alembic migrations are applied. Startup upgrades existing
versioned databases; an existing schema created without Alembic is recognized
and baselined before the additive monitoring-source migration is applied.

## API documentation

Interactive docs at `/docs` (Swagger) and `/redoc` once the backend is
running â€” 30+ endpoints across auth, dashboard, diagnostics, network,
speed test, monitoring (+ `/ws/monitor` WebSocket), alerts, packet capture,
analytics, reports, and settings. See `docs/architecture.md` for the
router-to-service map.

## Testing

```bash
cd backend
pytest -q          # 10 tests: auth flow + one integration test per Phase 3-9 feature, all via DEMO MODE

cd frontend
npx tsc -b && npx vite build   # type-check + production build
```

Every backend endpoint added in this project was exercised end-to-end
against a real (SQLite, for speed) database before this zip was built,
including the WebSocket monitoring loop and a real generated PDF.

## Computer Networks concepts demonstrated

See `docs/networking-concepts.md` â€” one section per concept (IP, ICMP,
DNS, HTTP, ARP, MAC, TCP/UDP, routing, packet capture, client-server,
WebSockets, statistical anomaly detection), each pointing at the exact
code that demonstrates it.

## DEMO MODE

Toggle in Settings, or `?demo=true` on most endpoints. When on, every
affected response carries `"simulated": true` and the UI shows a small
"Demo mode â€” simulated" badge. Simulated and real results are never mixed
in one response (spec section 33). Useful for presenting without a live
network, or on locked-down school/lab Wi-Fi where ICMP and raw sockets are
blocked.

## Limitations

- ICMP/traceroute/ARP/packet capture require OS binaries and, in Docker,
  `NET_RAW`/`NET_ADMIN` capabilities. Where unavailable, the app returns
  `"supported": false` with an explanation, or falls back to DEMO MODE â€”
  never fabricated real-mode data.
- Local device discovery does a light ping sweep of the local /24 and
  reads the OS ARP table; it is not a port or vulnerability scanner, and
  never targets anything outside the local subnet.
- Packet captures are held in-process (plus a JSON snapshot on disk) â€”
  fine for a single backend instance / course project, not designed to
  scale across multiple backend replicas.
- The speed test reports the median of three single-stream HTTP transfers
  to a public endpoint, checks the requested download byte count, and labels
  whether it ran on the Windows host or backend runtime. It remains an
  approximation, not a replacement for a multi-connection ISP speed test.
## Future scope

- Multi-connection speed test for closer parity with commercial tools.
- Per-metric custom alert rules (the `alert_rules` table exists; the UI
  currently drives alerting from the simpler Settings thresholds).
- Push notifications / email for fired alerts.
- Historical packet capture storage keyed by capture session, browsable
  from the Reports page.
