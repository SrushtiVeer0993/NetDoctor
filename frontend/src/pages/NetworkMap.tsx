import { useEffect, useState } from "react";
import axios from "axios";
import { Radar } from "lucide-react";
import DashboardLayout from "../layouts/DashboardLayout";
import DemoBadge from "../components/DemoBadge";
import { api } from "../services/api";
import type { DiscoveredDevice } from "../types";

export default function NetworkMap() {
  const [localIp, setLocalIp] = useState<string | null>(null);
  const [gateway, setGateway] = useState<string | null>(null);
  const [subnet, setSubnet] = useState<string | null>(null);
  const [interfaceName, setInterfaceName] = useState<string | null>(null);
  const [devices, setDevices] = useState<DiscoveredDevice[]>([]);
  const [simulated, setSimulated] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<DiscoveredDevice | null>(null);
  const [source, setSource] = useState<string | null>(null);
  const [hostWarning, setHostWarning] = useState<string | null>(null);
  const [discoveryMessage, setDiscoveryMessage] = useState<string | null>(null);
  const [discoverySkipped, setDiscoverySkipped] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadMap() {
    setLoading(true);
    try {
      const res = await api.get("/api/network/map");
      setLocalIp(res.data.local_ip ?? null);
      setGateway(res.data.gateway ?? null);
      setSubnet(res.data.subnet ?? null);
      setInterfaceName(res.data.interface_name ?? null);
      setDevices(res.data.devices || []);
      setSimulated(!!res.data.simulated);
      setSource(res.data.source ?? null);
      setHostWarning(
        res.data.host_agent?.available === false && res.data.source === "docker_container"
          ? res.data.host_agent.detail ?? "Windows host agent is unavailable; interface data is from the backend container."
          : null,
      );
      setError(null);
    } catch (err: unknown) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setError(typeof detail === "string" ? detail : "Could not load the network map.");
    } finally {
      setLoading(false);
    }
  }

  async function scan() {
    setScanning(true);
    setError(null);
    setDiscoveryMessage(null);
    setDiscoverySkipped(false);
    setSelected(null);
    try {
      const response = await api.post("/api/network/discover", { max_hosts: 1024 });
      await loadMap();
      const { status, detail, scanned_hosts: scanned, total_hosts: total } = response.data;
      const count = Number.isInteger(scanned) && Number.isInteger(total)
        ? ` Scanned ${scanned} of ${total} local addresses.`
        : "";
      const skipped = status === "skipped" || status === "unsupported";
      setDiscoverySkipped(skipped);
      const recovery = skipped && response.data.source === "docker_container"
        ? " Start the Windows host agent with .\\start-netdoctor.ps1, then scan again."
        : "";
      setDiscoveryMessage(`${detail ?? `Discovery ${status}.`}${count}${recovery}`);
    } catch (err: unknown) {
      const responseDetail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      const detail = typeof responseDetail === "string"
        ? responseDetail
        : Array.isArray(responseDetail)
          ? responseDetail.map((item: { msg?: string }) => item.msg).filter(Boolean).join("; ")
          : null;
      setError(detail || "Network discovery failed. The map still shows the last saved observations.");
    } finally {
      setScanning(false);
    }
  }

  useEffect(() => {
    void loadMap();
  }, []);

  const currentDevices = devices.filter((device) => device.status !== "not_seen");
  const previouslySeen = devices.filter((device) => device.status === "not_seen");

  return (
    <DashboardLayout>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-slate-100 flex items-center">
            Network Map <DemoBadge show={simulated} />
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Active interface and local neighbor observations; device links are not inferred
            {source && <span className="ml-2 text-slate-400">· Source: {source}</span>}
          </p>
        </div>
        <button
          onClick={scan}
          disabled={scanning}
          className="flex items-center gap-2 bg-healthy text-black font-medium text-sm px-4 py-2 rounded-md hover:opacity-90 disabled:opacity-50"
        >
          <Radar size={15} /> {scanning ? "Scanning…" : "Scan local subnet"}
        </button>
      </div>

      {hostWarning && (
        <div role="status" className="rounded-lg border border-warning/30 bg-warning/10 px-4 py-3 mb-4 text-sm text-warning">
          {hostWarning}
        </div>
      )}
      {discoveryMessage && (
        <div role="status" className={`rounded-lg border px-4 py-3 mb-4 text-sm ${discoverySkipped ? "border-warning/30 bg-warning/10 text-warning" : "border-border bg-panel text-slate-400"}`}>
          {discoveryMessage}
        </div>
      )}
      {error && (
        <div role="alert" className="rounded-lg border border-critical/30 bg-critical/10 px-4 py-3 mb-4 text-sm text-critical">
          {error}
        </div>
      )}

      <div className="rounded-lg border border-border bg-panel p-5 mb-6">
        <h2 className="text-sm font-medium text-slate-200 mb-1">Active interface</h2>
        <p className="text-xs text-slate-500 mb-4">
          These are route and address settings reported by the selected runtime, not a traced physical topology.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
          <div className="rounded-md border border-border bg-panel2 p-3">
            <div className="text-xs uppercase text-slate-500">This device</div>
            <div className="mt-1 font-mono text-sm text-slate-200">{loading ? "Loading…" : localIp ?? "Unavailable"}</div>
          </div>
          <div className="rounded-md border border-border bg-panel2 p-3">
            <div className="text-xs uppercase text-slate-500">Subnet</div>
            <div className="mt-1 font-mono text-sm text-slate-200">{subnet ?? "Unavailable"}</div>
          </div>
          <div className="rounded-md border border-border bg-panel2 p-3">
            <div className="text-xs uppercase text-slate-500">Default gateway</div>
            <div className="mt-1 font-mono text-sm text-slate-200">{gateway ?? "Unavailable"}</div>
          </div>
          <div className="rounded-md border border-border bg-panel2 p-3">
            <div className="text-xs uppercase text-slate-500">Interface</div>
            <div className="mt-1 text-sm text-slate-200">{interfaceName ?? "Unavailable"}</div>
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-panel p-5 mb-6">
        <div className="flex flex-wrap items-baseline justify-between gap-2 mb-1">
          <h2 className="text-sm font-medium text-slate-200">Observed LAN neighbors</h2>
          <span className="text-xs text-slate-500">
            {currentDevices.length} current observation(s) · {previouslySeen.length} not seen in the latest complete scan
          </span>
        </div>
        <p className="text-xs text-slate-500 mb-4">
          A responsive device answered ICMP. A neighbor-cache entry may be stale and does not confirm that the device is online.
        </p>
        {loading ? (
          <div className="text-sm text-slate-500">Loading observations…</div>
        ) : currentDevices.length === 0 ? (
          <div className="text-sm text-slate-500">No current neighbor observations for this subnet. Scan to refresh local observations.</div>
        ) : (
          <div className="flex flex-wrap gap-3">
            {currentDevices.map((device) => (
              <button
                key={`${device.subnet ?? subnet}:${device.ip}`}
                onClick={() => setSelected(device)}
                className="rounded-md border border-border px-3 py-2 text-left hover:border-healthy"
              >
                <span className="block font-mono text-xs text-slate-200">{device.hostname || device.ip}</span>
                <span className={`block mt-1 text-[10px] uppercase ${device.status === "responsive" ? "text-healthy" : "text-warning"}`}>
                  {simulated ? "Simulated observation" : device.status === "responsive" ? "ICMP responsive" : "Neighbor cache · unconfirmed"}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {previouslySeen.length > 0 && (
        <div className="rounded-lg border border-border bg-panel p-5 mb-6">
          <h2 className="text-sm font-medium text-slate-200 mb-1">Previously observed</h2>
          <p className="text-xs text-slate-500 mb-4">These addresses were absent from the latest complete scan. This does not prove they are offline.</p>
          <div className="flex flex-wrap gap-2">
            {previouslySeen.map((device) => (
              <button
                key={`${device.subnet ?? subnet}:${device.ip}`}
                onClick={() => setSelected(device)}
                className="rounded-md border border-border px-3 py-2 font-mono text-xs text-slate-400 hover:border-warning"
              >
                {device.hostname || device.ip}
              </button>
            ))}
          </div>
        </div>
      )}

      {selected && (
        <div className="rounded-lg border border-border bg-panel p-5">
          <div className="text-sm font-medium text-slate-200 mb-3">Observation details</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
            <div><span className="text-slate-500">IP:</span> <span className="text-slate-300 font-mono">{selected.ip}</span></div>
            <div><span className="text-slate-500">Subnet:</span> <span className="text-slate-300 font-mono">{selected.subnet ?? subnet ?? "unknown"}</span></div>
            <div><span className="text-slate-500">MAC:</span> <span className="text-slate-300 font-mono">{selected.mac ?? "unknown"}</span></div>
            <div><span className="text-slate-500">Hostname:</span> <span className="text-slate-300">{selected.hostname ?? "unknown"}</span></div>
            <div><span className="text-slate-500">Status:</span> <span className="text-slate-300">{simulated ? "simulated observation" : selected.status ?? "neighbor cache; reachability unconfirmed"}</span></div>
            <div><span className="text-slate-500">Last ICMP response:</span> <span className="text-slate-300">{!simulated && selected.status === "responsive" && selected.last_seen ? new Date(selected.last_seen).toLocaleString() : "not confirmed"}</span></div>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
