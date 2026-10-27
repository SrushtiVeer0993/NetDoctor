# Computer Networks concepts demonstrated

Each concept below is tied to the actual code that demonstrates it — this
is meant to be read alongside the source, not as a standalone essay.

## IP addressing
Local IP and subnet detection: `legacy_diagnostics._get_local_subnet_prefix()`,
surfaced on the Network Interface panel (`network/interface.py::get_active_interface_summary`).

## Default gateway
`legacy_diagnostics._get_default_gateway()` parses `ip route` (Linux),
`ipconfig` (Windows) or falls back to inferring it from the local IP.
Diagnostics and Network Map both use it.

## ICMP
`legacy_diagnostics._ping()` — used for gateway/internet reachability,
latency, packet loss, and the local-subnet ping sweep behind device
discovery. The gateway-ICMP nuance (spec section 4) is implemented
explicitly: a non-responding gateway is labeled `icmp_unavailable`, not
treated as proof of failure.

## RTT (round-trip time)
Parsed from ping output in `measure_latency()` — min/avg/max/jitter,
displayed on the Dashboard, Diagnostics, and Live Monitor pages.

## Packet loss
`measure_packet_loss()` — `(sent - received) / sent * 100`, kept
conceptually separate from latency throughout (spec section 6).

## DNS
`measure_dns_response_time()` (via `socket.gethostbyname`) resolves a
domain and times it. The DNS test page and Diagnostics both surface
resolved IP + response time + success/failure.

## HTTP/HTTPS
`test_websites()` distinguishes **reachable** (server responded at all)
from **successful request** (`status_code < 400`) from **application
error** (4xx/5xx) — a 403 is not "site down" (spec section 8).

## ARP
`discover_local_devices()` reads the OS ARP table after a light local
ping sweep, restricted to the machine's own /24 (never internet-wide —
spec section 11). Feeds the Network Map and `network_devices` table.

## MAC addresses
Surfaced alongside IPs in device discovery (Network Map) and in the
Network Interface panel (`network/{windows,linux,macos}.py::get_mac_address`).

## TCP/UDP, ports
Active Connections page (`network/{windows,linux,macos}.py::active_connections`,
parsing `ss`/`netstat`) — shows protocol, local/remote address:port, and
TCP state (ESTABLISHED, LISTENING, TIME_WAIT, …) with short explanations
in the UI.

## Routing / traceroute
`network/{windows,linux,macos}.py::traceroute` wraps `traceroute`/`tracert`,
hop-by-hop, with the spec's explicit rule that a non-responding hop is
labeled "no response" rather than assumed to be packet loss.

## Packet capture
`services/packet_capture.py` — Scapy-based, backend-only (the frontend
never touches raw sockets), parses Ethernet/IP/TCP/UDP layers per packet
for the click-to-inspect detail view. Requires root/admin privileges.

## Client-server architecture
React (client, `frontend/`) talks to FastAPI (server, `backend/`) over a
REST API + one WebSocket, with JWT bearer auth on every protected route.

## WebSockets
`/ws/monitor` (`api/monitoring.py`) streams a JSON measurement every N
seconds for Live Monitoring, including in-band alert notifications when a
threshold breach fires.

## Statistical anomaly detection
`services/anomaly.py` — trailing moving average + rolling standard
deviation + z-score against a historical baseline, with an optional
Isolation Forest (scikit-learn) pass layered on top. Never called "AI".
