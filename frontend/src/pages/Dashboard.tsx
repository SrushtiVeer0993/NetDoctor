import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Activity, AlertTriangle, ArrowRight, CheckCircle2, Clock3, Gauge, Globe2, RefreshCw, Router, Search, Wifi } from "lucide-react";
import DashboardLayout from "../layouts/DashboardLayout";
import StatCard from "../components/StatCard";
import HealthScoreGauge from "../components/HealthScoreGauge";
import DemoBadge from "../components/DemoBadge";
import { api } from "../services/api";
import type { DashboardData } from "../types";

function fmtMs(value: number | null) {
  return value === null || value === undefined ? "—" : `${value} ms`;
}

function fmtPct(value: number | null) {
  return value === null || value === undefined ? "Unavailable" : `${value}%`;
}

function timeAgo(timestamp: string) {
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - new Date(timestamp).getTime()) / 1000));
  const units: [number, Intl.RelativeTimeFormatUnit][] = [
    [60, "second"], [60, "minute"], [24, "hour"], [30, "day"], [12, "month"], [Number.MAX_SAFE_INTEGER, "year"],
  ];
  let value = elapsedSeconds;
  let unit: Intl.RelativeTimeFormatUnit = "second";
  for (const [divisor, nextUnit] of units) {
    if (value < divisor) break;
    value = Math.floor(value / divisor);
    unit = nextUnit;
  }
  return new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }).format(-value, unit);
}

function sourceLabel(source: string | undefined, simulated: boolean) {
  if (simulated) return "Demo data";
  if (source === "windows_host") return "Windows host";
  if (source === "docker_container") return "Docker container";
  if (source) return source.replace(/_/g, " ");
  return "Real measurement";
}

function errorMessage(error: any) {
  const detail = error?.response?.data?.detail;
  return typeof detail === "string" ? detail : error?.message || "Could not load dashboard data.";
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load(isRefresh = false) {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const response = await api.get<DashboardData>("/api/dashboard");
      setData(response.data);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => { void load(); }, []);

  const latest = data?.latest;
  const needsAttention = latest?.internet_reachable === false || (latest?.health_score ?? 100) < 50;
  const inconclusive = !needsAttention && latest && latest.internet_reachable === null;

  return (
    <DashboardLayout>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight text-slate-100">Network overview</h1>
            <DemoBadge show={!!latest?.simulated} />
          </div>
          <p className="mt-1 text-sm text-slate-500">
            {latest ? `Last checked ${timeAgo(latest.created_at)} · ${sourceLabel(latest.source, latest.simulated)}` : "A clear view of your latest network diagnosis"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => void load(true)}
            disabled={loading || refreshing}
            aria-label="Refresh dashboard"
            className="inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm text-slate-300 hover:border-slate-500 disabled:opacity-50"
          >
            <RefreshCw size={15} className={refreshing ? "animate-spin" : ""} /> Refresh
          </button>
          <Link
            to="/diagnostics"
            className="inline-flex items-center gap-2 rounded-md bg-healthy px-4 py-2 text-sm font-medium text-black hover:opacity-90"
          >
            <Activity size={16} /> Run diagnosis
          </Link>
        </div>
      </div>

      {loading && (
        <div role="status" className="space-y-4">
          <div className="h-16 animate-pulse rounded-lg border border-border bg-panel" />
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 6 }, (_, index) => <div key={index} className="h-24 animate-pulse rounded-lg border border-border bg-panel" />)}
          </div>
          <span className="sr-only">Loading dashboard…</span>
        </div>
      )}

      {error && (
        <div role="alert" className="rounded-lg border border-red-900 bg-red-950/30 p-5 text-sm text-red-300">
          <p>Dashboard data could not be loaded: {error}</p>
          <button onClick={() => void load()} className="mt-3 rounded-md border border-red-800 px-3 py-1.5 hover:bg-red-950">Retry</button>
        </div>
      )}

      {!loading && !error && data && !data.has_data && (
        <div className="rounded-xl border border-border bg-panel px-6 py-12 text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-healthy/10 text-healthy">
            <Activity size={25} />
          </div>
          <h2 className="mt-4 text-lg font-medium text-slate-100">Start with a network diagnosis</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-slate-500">
            Measure gateway and internet reachability, latency, packet loss, DNS response, and local devices.
          </p>
          <Link to="/diagnostics" className="mt-5 inline-flex items-center gap-2 rounded-md bg-healthy px-4 py-2 text-sm font-medium text-black hover:opacity-90">
            Run your first diagnosis <ArrowRight size={15} />
          </Link>
        </div>
      )}

      {!loading && latest && (
        <div className="space-y-5">
          <section className={`flex items-start gap-3 rounded-lg border p-4 ${needsAttention ? "border-red-900/70 bg-red-950/20" : inconclusive ? "border-amber-900/70 bg-amber-950/20" : "border-emerald-900/70 bg-emerald-950/20"}`}>
            {needsAttention
              ? <AlertTriangle size={18} className="mt-0.5 shrink-0 text-red-400" />
              : inconclusive
              ? <AlertTriangle size={18} className="mt-0.5 shrink-0 text-amber-400" />
              : <CheckCircle2 size={18} className="mt-0.5 shrink-0 text-emerald-400" />}
            <div>
              <h2 className={`text-sm font-medium ${needsAttention ? "text-red-300" : inconclusive ? "text-amber-300" : "text-emerald-300"}`}>
                {needsAttention ? "Connectivity needs attention" : inconclusive ? "Connectivity could not be confirmed" : "Internet connection confirmed"}
              </h2>
              <p className="mt-1 text-xs text-slate-400">
                {needsAttention
                  ? "The latest diagnostic could not establish internet reachability or returned a low health score. Review the findings below."
                  : inconclusive
                  ? "The available check was inconclusive. Some networks block probes, so this alone does not prove the connection is down."
                  : "The latest diagnostic confirmed internet reachability. Review the measurements below for delays or other issues."}
              </p>
            </div>
          </section>

          <section className="grid grid-cols-1 gap-4 lg:grid-cols-12">
            <div className="lg:col-span-4">
              <HealthScoreGauge score={latest.health_score} />
              <div className="mt-3 rounded-lg border border-border bg-panel p-4">
                <div className="flex items-center gap-2 text-sm font-medium text-slate-200">
                  <Clock3 size={15} className="text-slate-500" /> Latest diagnosis
                </div>
                <p className="mt-1 text-sm text-slate-400">{new Date(latest.created_at).toLocaleString()}</p>
                <p className="mt-2 text-xs text-slate-500">Source: {sourceLabel(latest.source, latest.simulated)}</p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:col-span-8">
              <StatCard
                label="Internet"
                value={latest.internet_reachable === null ? "Unconfirmed" : latest.internet_reachable ? "Connected" : "Unreachable"}
                sub="TCP connectivity check"
                icon={Globe2}
                tone={latest.internet_reachable === null ? "warning" : latest.internet_reachable ? "healthy" : "critical"}
              />
              <StatCard
                label="Gateway"
                value={latest.gateway_reachable === null ? "Unavailable" : latest.gateway_reachable ? "Responded" : "No ICMP reply"}
                sub="A missing ping reply is inconclusive"
                icon={Router}
                tone={latest.gateway_reachable === null ? "neutral" : latest.gateway_reachable ? "healthy" : "warning"}
              />
              <StatCard label="Latency" value={fmtMs(latest.latency_avg_ms)} sub="Average response time" icon={Gauge} />
              <StatCard
                label="Packet loss"
                value={fmtPct(latest.packet_loss_pct)}
                sub={latest.packet_loss_pct == null ? "ICMP measurement unavailable" : "Measured by ICMP probes"}
                icon={Activity}
                tone={latest.packet_loss_pct == null ? "info" : latest.packet_loss_pct > 5 ? "critical" : latest.packet_loss_pct > 0 ? "warning" : "healthy"}
              />
              <StatCard label="DNS response" value={fmtMs(latest.dns_response_ms)} sub="Lookup time" icon={Wifi} />
              <StatCard
                label="Local devices"
                value={latest.device_discovery_status === "completed"
                  ? `${latest.devices_discovered} found`
                  : latest.device_discovery_status === "partial"
                  ? `${latest.devices_discovered} found · partial`
                  : latest.device_discovery_status === "skipped"
                  ? "Not scanned"
                  : latest.device_discovery_status.replace(/_/g, " ")}
                sub="Local subnet discovery"
                icon={Search}
                tone={latest.device_discovery_status === "partial" ? "warning" : "neutral"}
              />
            </div>
          </section>

          <section className="grid grid-cols-1 gap-4 lg:grid-cols-5">
            <div className="rounded-lg border border-border bg-panel p-5 lg:col-span-3">
              <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-200">
                Latest finding <DemoBadge show={latest.simulated} />
              </div>
              <p className="text-sm leading-6 text-slate-400">{latest.top_finding || "No finding was recorded for this diagnosis."}</p>
              {latest.recommendations.length > 0 && (
                <ul className="mt-4 space-y-2 border-t border-border pt-3">
                  {latest.recommendations.slice(0, 3).map((recommendation, index) => (
                    <li key={`${index}-${recommendation}`} className="flex gap-2 text-sm text-slate-400">
                      <span className="text-healthy">›</span><span>{recommendation}</span>
                    </li>
                  ))}
                </ul>
              )}
              <Link to="/diagnostics" className="mt-4 inline-flex items-center gap-1 text-xs text-healthy hover:underline">
                Run another diagnosis <ArrowRight size={13} />
              </Link>
            </div>

            <div className="rounded-lg border border-border bg-panel p-5 lg:col-span-2">
              <div className="text-sm font-medium text-slate-200">Explore your network</div>
              <p className="mt-1 text-xs text-slate-500">Open a focused view of your measurements.</p>
              <div className="mt-4 space-y-2">
                <Link to="/analytics" className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm text-slate-300 hover:border-healthy/50 hover:text-healthy">
                  Analytics <ArrowRight size={14} />
                </Link>
                <Link to="/network-map" className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm text-slate-300 hover:border-healthy/50 hover:text-healthy">
                  Network map <ArrowRight size={14} />
                </Link>
                <Link to="/live-monitor" className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm text-slate-300 hover:border-healthy/50 hover:text-healthy">
                  Live monitor <ArrowRight size={14} />
                </Link>
              </div>
            </div>
          </section>

          <section className="rounded-lg border border-border bg-panel p-5">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-medium text-slate-200">Recent diagnoses</h2>
                <p className="mt-1 text-xs text-slate-500">Latest {data.recent_tests.length} saved run(s)</p>
              </div>
              <Link to="/reports" className="inline-flex items-center gap-1 text-xs text-healthy hover:underline">
                View reports <ArrowRight size={13} />
              </Link>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[620px] text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wide text-slate-600">
                    <th className="pb-2 font-normal">Time</th>
                    <th className="pb-2 font-normal">Health</th>
                    <th className="pb-2 font-normal">Latency</th>
                    <th className="pb-2 font-normal">Packet loss</th>
                    <th className="pb-2 font-normal">Source</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_tests.map((run) => (
                    <tr key={run.id} className="border-t border-border">
                      <td className="py-2.5 text-slate-400">{new Date(run.created_at).toLocaleString()}</td>
                      <td className="py-2.5 font-mono-num text-slate-200">{run.health_score}/100</td>
                      <td className="py-2.5 font-mono-num text-slate-400">{fmtMs(run.latency_avg_ms)}</td>
                      <td className="py-2.5 font-mono-num text-slate-400">{fmtPct(run.packet_loss_pct)}</td>
                      <td className="py-2.5 text-slate-400">{sourceLabel(run.source, run.simulated)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}
    </DashboardLayout>
  );
}
