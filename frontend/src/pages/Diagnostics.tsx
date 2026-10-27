import { useEffect, useRef, useState } from "react";
import axios from "axios";
import DashboardLayout from "../layouts/DashboardLayout";
import { api } from "../services/api";
import type { DiagnosisResult, UserSettingsData } from "../types";
import DemoBadge from "../components/DemoBadge";

export default function Diagnostics() {
  const [running, setRunning] = useState(false);
  const [discoverDevices, setDiscoverDevices] = useState(false);
  const [result, setResult] = useState<DiagnosisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => () => activeRequest.current?.abort(), []);

  async function runDiagnosis() {
    if (activeRequest.current) return;
    const controller = new AbortController();
    activeRequest.current = controller;
    setRunning(true);
    setError(null);
    setResult(null);

    try {
      const settings = await api.get<UserSettingsData>("/api/settings");
      const res = await api.post<DiagnosisResult>("/api/diagnostics/full", {
        external_host: settings.data.default_ping_target,
        dns_domain: settings.data.default_dns_domain,
        websites: ["https://www.google.com", "https://www.wikipedia.org"],
        discover_devices: discoverDevices,
      }, { signal: controller.signal });
      setResult(res.data);
    } catch (err: unknown) {
      if (axios.isCancel(err)) {
        setError("Diagnosis was cancelled.");
      } else {
        const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
        setError(typeof detail === "string" ? detail : "Diagnosis failed to run.");
      }
    } finally {
      if (activeRequest.current === controller) activeRequest.current = null;
      setRunning(false);
    }
  }

  const r = result?.result_json;

  return (
    <DashboardLayout>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-slate-100 flex items-center gap-2">
            Full Network Diagnostics <DemoBadge show={!!r?.simulated} />
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Measure → Analyze → Identify probable problem → Recommend
            {r?.source && <span className="ml-2 text-slate-400">· Source: {r.source}</span>}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-4 mb-5">
        <label className="flex items-center gap-2 text-sm text-slate-400">
          <input
            type="checkbox"
            checked={discoverDevices}
            onChange={(event) => setDiscoverDevices(event.target.checked)}
            disabled={running}
            className="accent-healthy"
          />
          Discover devices on my local network
        </label>
        <button
          onClick={runDiagnosis}
          disabled={running}
          className="bg-healthy text-black font-medium text-sm px-4 py-2 rounded-md hover:opacity-90 disabled:opacity-50"
        >
          {running ? "Running…" : "Run Full Diagnosis"}
        </button>
        {running && (
          <button
            onClick={() => activeRequest.current?.abort()}
            className="text-sm text-slate-400 hover:text-slate-200"
          >
            Cancel
          </button>
        )}
      </div>

      {running && (
        <div role="status" className="rounded-lg border border-border bg-panel p-5 mb-5 text-sm text-slate-300">
          Running network measurements. This may take a few moments…
        </div>
      )}

      {error && (
        <div className="text-sm text-critical bg-critical/10 border border-critical/30 rounded-md px-3 py-2 mb-5">
          {error}
        </div>
      )}

      {r && (
        <div className="space-y-5">
          {r.host_agent && !r.host_agent.available && r.source === "docker_container" && (
            <div role="status" className="rounded-lg border border-warning/30 bg-warning/10 p-4 text-sm text-warning">
              Windows host measurements are unavailable. Results below come from {r.source ?? "the backend runtime"}, not the laptop’s Wi-Fi adapter.
              {r.host_agent.detail && <div className="mt-1 text-xs text-slate-400">{r.host_agent.detail}</div>}
            </div>
          )}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="rounded-lg border border-border bg-panel px-4 py-3">
              <div className="text-xs text-slate-500 uppercase">Gateway</div>
              <div className={`mt-1 font-medium ${r.gateway.reachable ? "text-healthy" : "text-warning"}`}>
                {r.gateway.error_type
                  ? "Ping tool failed"
                  : r.gateway.reachable === null
                  ? "Unavailable"
                  : r.gateway.reachable ? "ICMP reachable" : "ICMP unavailable"}
              </div>
              <div className="text-xs text-slate-600 mt-0.5">
                {r.gateway.gateway_ip ?? r.interface?.gateway_ipv6 ?? "No default gateway"}
              </div>
              {r.gateway.interface_name && (
                <div className="text-xs text-slate-600 mt-0.5">
                  {r.gateway.interface_name} · {r.gateway.interface_type ?? "interface"}
                </div>
              )}
              {r.gateway.detail && <div className="text-xs text-warning mt-1">{r.gateway.detail}</div>}
            </div>
            <div className="rounded-lg border border-border bg-panel px-4 py-3">
              <div className="text-xs text-slate-500 uppercase">Internet</div>
              <div className={`mt-1 font-medium ${r.internet.reachable === true ? "text-healthy" : "text-warning"}`}>
                {r.internet.reachable === true
                  ? "Reachable"
                  : r.internet.reachable === false ? "Unreachable" : "Unconfirmed"}
              </div>
              <div className="text-xs text-slate-600 mt-0.5">
                {r.internet.method ?? `ICMP target: ${r.internet.target}`}
              </div>
              {r.internet.icmp_unavailable && r.internet.reachable === true && (
                <div className="text-xs text-slate-500 mt-0.5">ICMP did not respond; TCP connectivity succeeded.</div>
              )}
              {r.internet.icmp_error_type && (
                <div className="text-xs text-warning mt-0.5">ICMP diagnostic tool: {r.internet.icmp_error_type}</div>
              )}
            </div>
            <div className="rounded-lg border border-border bg-panel px-4 py-3">
              <div className="text-xs text-slate-500 uppercase">Latency</div>
              <div className="mt-1 font-medium text-slate-200 font-mono-num">
                {r.latency.avg_ms ?? "—"} ms avg
              </div>
              <div className="text-xs text-slate-600 mt-0.5">
                min {r.latency.min_ms ?? "—"} / max {r.latency.max_ms ?? "—"} / jitter {r.latency.jitter_ms ?? "—"}
              </div>
            </div>
            <div className="rounded-lg border border-border bg-panel px-4 py-3">
              <div className="text-xs text-slate-500 uppercase">Packet Loss</div>
              <div className="mt-1 font-medium text-slate-200 font-mono-num">
                {r.packet_loss.error_type
                  ? "Ping tool failed"
                  : r.packet_loss.icmp_unavailable
                  ? "ICMP unavailable"
                  : r.packet_loss.loss_pct == null ? "Unavailable" : `${r.packet_loss.loss_pct}%`}
              </div>
              <div className="text-xs text-slate-600 mt-0.5">
                {r.packet_loss.received}/{r.packet_loss.sent} received
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-border bg-panel p-5">
            <div className="text-sm font-medium text-slate-200 mb-2">DNS</div>
            <div className="text-sm text-slate-400">
              {r.dns.domain} → {r.dns.resolved_ip ?? (r.dns.success ? "unavailable" : "resolution failed")} ({r.dns.response_ms ?? "—"} ms)
            </div>
            {r.dns.error && <div className="text-xs text-warning mt-1">{r.dns.error}</div>}
          </div>

          {r.websites.length > 0 && (
            <div className="rounded-lg border border-border bg-panel p-5">
              <div className="text-sm font-medium text-slate-200 mb-3">Website tests</div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-slate-600 uppercase">
                    <th className="pb-2 font-normal">URL</th>
                    <th className="pb-2 font-normal">Status</th>
                    <th className="pb-2 font-normal">Response</th>
                  </tr>
                </thead>
                <tbody>
                  {r.websites.map((w) => (
                    <tr key={w.url} className="border-t border-border">
                      <td className="py-2 text-slate-300">{w.url}</td>
                      <td className="py-2">
                        {w.reachable ? (
                          <span className={w.successful_request ? "text-healthy" : "text-warning"}>
                            {w.status_code}
                          </span>
                        ) : (
                          <div>
                            <span className="text-critical">unreachable</span>
                            {w.error_type && (
                              <div className="mt-1 text-xs text-slate-500">{w.error_type}: {w.error}</div>
                            )}
                          </div>
                        )}
                      </td>
                      <td className="py-2 text-slate-400 font-mono-num">{w.response_ms ?? "—"} ms</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {r.devices && (
            <div className="rounded-lg border border-border bg-panel p-5">
              <div className="text-sm font-medium text-slate-200 mb-2">Local device discovery</div>
              <p className="text-sm text-slate-400">
                {r.devices.status === "skipped"
                  ? r.devices.detail || "Skipped — device discovery was not requested."
                  : (r.devices.status === "empty" || r.devices.status === "completed") && r.devices.devices?.length === 0
                  ? `Completed, but no neighbor entries were found. This does not prove that no other devices are present.${r.devices.subnet ? ` Subnet: ${r.devices.subnet}.` : ""}`
                  : r.devices.status === "success" || r.devices.status === "completed"
                  ? `Completed — ${r.devices.devices?.length ?? 0} responsive device(s) found.`
                  : r.devices.status === "partial"
                  ? `Partial results — ${r.devices.devices?.length ?? 0} device(s). ${r.devices.detail ?? ""}`
                  : r.devices.detail || `Discovery ${r.devices.status || "status unavailable"}.`}
              </p>
              {r.devices.source && <div className="text-xs text-slate-600 mt-1">Source: {r.devices.source}</div>}
            </div>
          )}

          <div className="rounded-lg border border-border bg-panel p-5">
            <div className="text-sm font-medium text-slate-200 mb-3">Findings</div>
            <div className="space-y-3">
              {r.findings.map((f, i) => (
                <div key={i} className="text-sm">
                  <div className="flex items-center gap-2">
                    <span
                      className={
                        f.severity === "critical"
                          ? "text-critical"
                          : f.severity === "warning"
                          ? "text-warning"
                          : f.severity === "healthy"
                          ? "text-healthy"
                          : "text-info"
                      }
                    >
                      ●
                    </span>
                    <span className="text-slate-500 text-xs uppercase">
                      {f.severity} · {f.confidence} confidence
                    </span>
                  </div>
                  <p className="text-slate-300 mt-1 ml-4">{f.text}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-border bg-panel p-5">
            <div className="text-sm font-medium text-slate-200 mb-2">Recommendations</div>
            <ul className="space-y-1.5">
              {r.recommendations.map((rec, i) => (
                <li key={i} className="text-sm text-slate-400 flex gap-2">
                  <span className="text-healthy">›</span> {rec}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
