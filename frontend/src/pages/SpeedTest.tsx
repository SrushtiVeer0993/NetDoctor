import { useState } from "react";
import { Gauge } from "lucide-react";
import DashboardLayout from "../layouts/DashboardLayout";
import DemoBadge from "../components/DemoBadge";
import { api } from "../services/api";
import type { SpeedTestResult } from "../types";

export default function SpeedTest() {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<SpeedTestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.post<SpeedTestResult>("/api/speedtest", {});
      setResult(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Speed test failed.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <DashboardLayout>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-slate-100 flex items-center">
            Speed Test <DemoBadge show={!!result?.simulated} />
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">Download / upload throughput measurement</p>
        </div>
        <button
          onClick={run}
          disabled={running}
          className="flex items-center gap-2 bg-healthy text-black font-medium text-sm px-4 py-2 rounded-md hover:opacity-90 disabled:opacity-50"
        >
          <Gauge size={15} /> {running ? "Testing…" : "Run Speed Test"}
        </button>
      </div>

      {error && (
        <div className="text-sm text-critical bg-critical/10 border border-critical/30 rounded-md px-3 py-2 mb-5">
          {error}
        </div>
      )}

      {running && !result && (
        <div className="rounded-lg border border-border bg-panel p-10 text-center text-slate-500">
          Measuring download and upload throughput…
        </div>
      )}

      {result && (
        <div className="space-y-5">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div className="rounded-lg border border-border bg-panel p-8 text-center">
              <div className="text-xs text-slate-500 uppercase tracking-wide">Download</div>
              <div className="mt-2 text-5xl font-mono-num font-bold text-healthy">
                {result.download.mbps ?? "—"}
              </div>
              <div className="text-sm text-slate-500 mt-1">Mbps</div>
              {!result.download.success && result.download.error && (
                <div className="mt-2 text-xs text-warning">Download failed: {result.download.error}</div>
              )}
            </div>
            <div className="rounded-lg border border-border bg-panel p-8 text-center">
              <div className="text-xs text-slate-500 uppercase tracking-wide">Upload</div>
              <div className="mt-2 text-5xl font-mono-num font-bold text-info">
                {result.upload.mbps ?? "—"}
              </div>
              <div className="text-sm text-slate-500 mt-1">Mbps</div>
              {!result.upload.success && result.upload.error && (
                <div className="mt-2 text-xs text-warning">Upload failed: {result.upload.error}</div>
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="rounded-lg border border-border bg-panel px-4 py-3">
              <div className="text-xs text-slate-500 uppercase">Latency</div>
              <div className="mt-1 text-xl font-mono-num text-slate-200">{result.latency_ms ?? "—"} ms</div>
            </div>
            <div className="rounded-lg border border-border bg-panel px-4 py-3">
              <div className="text-xs text-slate-500 uppercase">Jitter</div>
              <div className="mt-1 text-xl font-mono-num text-slate-200">{result.jitter_ms ?? "—"} ms</div>
            </div>
          </div>

          <div className="rounded-lg border border-border bg-panel p-4">
            <div className="text-xs text-slate-500 uppercase mb-1">Methodology</div>
            <p className="text-sm text-slate-400">{result.methodology}</p>
            {result.source && (
              <p className="text-xs text-slate-500 mt-2">
                Measurement source: {result.source === "windows_host" ? "Windows host" : result.source === "docker_container" ? "Docker container" : "backend runtime"}
              </p>
            )}
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
