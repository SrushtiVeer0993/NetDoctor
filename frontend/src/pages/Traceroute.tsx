import { FormEvent, useState } from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import DemoBadge from "../components/DemoBadge";
import { api } from "../services/api";
import type { TracerouteResult } from "../types";

export default function Traceroute() {
  const [target, setTarget] = useState("google.com");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<TracerouteResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.post<TracerouteResult>("/api/network/traceroute", { target });
      setResult(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Traceroute failed.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <DashboardLayout>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-slate-100 flex items-center">
          Traceroute <DemoBadge show={!!result?.simulated} />
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Hop-by-hop path to a destination. Some routers may not respond to probes — a missing hop
          does not automatically mean packet loss.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex gap-3 mb-6">
        <input
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          placeholder="Target (e.g. google.com)"
          className="flex-1 max-w-sm rounded-md bg-panel2 border border-border px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-healthy"
        />
        <button
          type="submit"
          disabled={running || !target}
          className="bg-healthy text-black font-medium text-sm px-4 py-2 rounded-md hover:opacity-90 disabled:opacity-50"
        >
          {running ? "Tracing…" : "Run Traceroute"}
        </button>
      </form>

      {error && (
        <div className="text-sm text-critical bg-critical/10 border border-critical/30 rounded-md px-3 py-2 mb-5">
          {error}
        </div>
      )}

      {result && !result.supported && (
        <div className="text-sm text-warning bg-warning/10 border border-warning/30 rounded-md px-3 py-2 mb-5">
          Unavailable on this system{result.error ? `: ${result.error}` : "."}
        </div>
      )}

      {result && result.supported && (
        <div>
          {result.error && (
            <div role="status" className="text-sm text-warning bg-warning/10 border border-warning/30 rounded-md px-3 py-2 mb-5">
              {result.error}
            </div>
          )}
          {typeof result.destination_reached === "boolean" && (
            <div role="status" className={`text-sm rounded-md px-3 py-2 mb-5 ${result.destination_reached ? "text-healthy bg-healthy/10 border border-healthy/30" : "text-warning bg-warning/10 border border-warning/30"}`}>
              {result.destination_reached
                ? "Destination reached; traceroute completed."
                : "Destination was not confirmed. Some networks filter traceroute probes."}
            </div>
          )}
          {result.hops.length === 0 ? (
            <div className="rounded-lg border border-border bg-panel p-5 text-sm text-slate-400">
              No hop responses were returned.
            </div>
          ) : (
        <div className="rounded-lg border border-border bg-panel p-5">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-600 uppercase">
                <th className="pb-2 font-normal w-16">Hop</th>
                <th className="pb-2 font-normal">IP</th>
                <th className="pb-2 font-normal">Latency</th>
                <th className="pb-2 font-normal">Status</th>
              </tr>
            </thead>
            <tbody>
              {result.hops.map((h) => (
                <tr key={h.hop} className="border-t border-border">
                  <td className="py-2 text-slate-400 font-mono-num">{h.hop}</td>
                  <td className="py-2 text-slate-200 font-mono">{h.ip ?? "*"}</td>
                  <td className="py-2 text-slate-400 font-mono-num">{h.latency_ms ?? "—"} ms</td>
                  <td className="py-2">
                    <span className={h.status === "no_response" ? "text-slate-600" : "text-healthy"}>
                      {h.status === "destination" ? "Destination" : h.status === "responded" ? "Responded" : "No response"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
          )}
        </div>
      )}
    </DashboardLayout>
  );
}
