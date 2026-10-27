import { useEffect, useState } from "react";
import axios from "axios";
import { RefreshCw } from "lucide-react";
import DashboardLayout from "../layouts/DashboardLayout";
import DemoBadge from "../components/DemoBadge";
import { api } from "../services/api";
import type { ConnectionRow } from "../types";

const FILTERS = ["ALL", "TCP", "UDP", "ESTABLISHED", "LISTENING"];

const STATE_HELP: Record<string, string> = {
  ESTABLISHED: "Active, open connection",
  LISTENING: "Waiting for incoming connections",
  TIME_WAIT: "Recently closed, waiting to fully release",
  UNCONN: "UDP socket without a connected remote endpoint",
  STATELESS: "UDP — no connection state tracked",
};

export default function Connections() {
  const [connections, setConnections] = useState<ConnectionRow[]>([]);
  const [simulated, setSimulated] = useState(false);
  const [supported, setSupported] = useState(true);
  const [source, setSource] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("ALL");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get("/api/network/connections");
      setConnections(res.data.connections || []);
      setSimulated(!!res.data.simulated);
      setSupported(res.data.supported !== false);
      setSource(res.data.source ?? null);
      setError(res.data.error ?? null);
    } catch (err: unknown) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setConnections([]);
      setSupported(false);
      setError(typeof detail === "string" ? detail : "Could not load active connections.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const filtered = connections.filter((c) => {
    if (filter === "ALL") return true;
    if (filter === "TCP" || filter === "UDP") return c.protocol === filter;
    return c.state === filter;
  });

  return (
    <DashboardLayout>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-slate-100 flex items-center">
            Active Connections <DemoBadge show={simulated} />
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Current TCP/UDP sockets{source === "docker_container" ? " reported by the Docker container" : " on this machine"}
            {source && <span className="ml-2 text-slate-400">Source: {source}</span>}
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-2 text-sm text-slate-400 hover:text-slate-200 border border-border px-3 py-2 rounded-md disabled:opacity-50"
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      <div className="flex gap-2 mb-4">
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`text-xs px-3 py-1.5 rounded-md border ${
              filter === f ? "border-healthy text-healthy" : "border-border text-slate-500"
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {loading && <div className="text-sm text-slate-500">Loading…</div>}

      {!loading && !supported && (
        <div className="text-sm text-warning bg-warning/10 border border-warning/30 rounded-md px-3 py-2">
          {error || "Unavailable on this system."}
          {source === "docker_container" && " Start or restart the Windows host agent, then refresh."}
        </div>
      )}

      {!loading && supported && error && (
        <div role="status" className="text-sm text-warning bg-warning/10 border border-warning/30 rounded-md px-3 py-2 mb-4">
          {error}
        </div>
      )}

      {!loading && supported && (
        <div className="rounded-lg border border-border bg-panel p-5">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-600 uppercase">
                <th className="pb-2 font-normal">Protocol</th>
                <th className="pb-2 font-normal">Local</th>
                <th className="pb-2 font-normal">Remote</th>
                <th className="pb-2 font-normal">State</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((c, i) => (
                <tr key={i} className="border-t border-border">
                  <td className="py-2 text-slate-300">{c.protocol}</td>
                  <td className="py-2 text-slate-400 font-mono">
                    {c.local_ip}:{c.local_port ?? "—"}
                  </td>
                  <td className="py-2 text-slate-400 font-mono">
                    {c.remote_ip ? `${c.remote_ip}:${c.remote_port}` : "—"}
                  </td>
                  <td className="py-2 text-slate-300" title={STATE_HELP[c.state] || ""}>
                    {c.state}
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={4} className="py-6 text-center text-slate-600">
                    No matching connections.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </DashboardLayout>
  );
}
