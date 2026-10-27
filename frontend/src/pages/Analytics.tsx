import { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import DashboardLayout from "../layouts/DashboardLayout";
import { api } from "../services/api";
import type { AnalyticsData } from "../types";

const RANGES = [
  { key: "today", label: "Today" },
  { key: "7d", label: "7 Days" },
  { key: "30d", label: "30 Days" },
];

const CHARTS = [
  { key: "latency_avg_ms", label: "Latency", color: "#22c55e", unit: "ms" },
  { key: "packet_loss_pct", label: "Packet loss", color: "#ef4444", unit: "%" },
  { key: "health_score", label: "Health score", color: "#3b82f6", unit: "points" },
] as const;

export default function Analytics() {
  const [range, setRange] = useState("7d");
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      const params: Record<string, string> = { range };
      if (range === "today") {
        const now = new Date();
        params.start = new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString();
        params.end = now.toISOString();
      }

      try {
        const res = await api.get<AnalyticsData>("/api/analytics", { params });
        if (!cancelled) setData(res.data);
      } catch (err: any) {
        if (!cancelled) {
          setData(null);
          const detail = err?.response?.data?.detail;
          setError(typeof detail === "string" ? detail : err?.message || "Could not load analytics.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => { cancelled = true; };
  }, [range, reloadKey]);

  const chartData = (data?.series || []).map((point) => ({
    timestamp: point.timestamp,
    latency_avg_ms: point.latency_avg_ms,
    packet_loss_pct: point.packet_loss_pct,
    health_score: point.health_score,
    simulated: point.simulated,
  }));

  return (
    <DashboardLayout>
      <div className="flex items-center justify-between mb-6 gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Analytics</h1>
          <p className="text-sm text-slate-500 mt-0.5">Historical trends from your diagnostic runs</p>
          {data?.stats_source === "mixed" && (
            <p className="text-xs text-info mt-1">
              Summary statistics include both real and demo runs. Each chart point identifies its source.
            </p>
          )}
          {data?.stats_source === "simulated" && (
            <p className="text-xs text-info mt-1">These results are from demo runs.</p>
          )}
        </div>
        <div className="flex gap-2 shrink-0">
          {RANGES.map((item) => (
            <button
              key={item.key}
              onClick={() => setRange(item.key)}
              aria-pressed={range === item.key}
              className={`text-xs px-3 py-1.5 rounded-md border ${range === item.key ? "border-healthy text-healthy" : "border-border text-slate-500"}`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {loading && <div className="text-sm text-slate-500">Loading…</div>}

      {!loading && error && (
        <div role="alert" className="rounded-lg border border-red-900 bg-red-950/30 p-5 text-sm text-red-300">
          <p>Analytics could not be loaded: {error}</p>
          <button
            onClick={() => setReloadKey((key) => key + 1)}
            className="mt-3 rounded-md border border-red-800 px-3 py-1.5 text-red-200 hover:bg-red-950"
          >
            Retry
          </button>
        </div>
      )}

      {!loading && !error && (!data || !data.has_data) && (
        <div className="rounded-lg border border-border bg-panel p-8 text-center text-slate-500">
          No diagnostic history in this range yet. Run diagnoses over time to build trends.
        </div>
      )}

      {!loading && !error && data?.has_data && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {(["health_score", "latency_avg_ms", "packet_loss_pct", "dns_response_ms"] as const).map((key) => {
              const stats = data.stats[key];
              const labels: Record<string, string> = {
                health_score: "Health Score", latency_avg_ms: "Latency", packet_loss_pct: "Packet Loss", dns_response_ms: "DNS",
              };
              return (
                <div key={key} className="rounded-lg border border-border bg-panel px-4 py-3">
                  <div className="text-xs text-slate-500 uppercase">{labels[key]}</div>
                  {stats ? (
                    <>
                      <div className="mt-1 text-xl font-mono-num text-slate-100">{stats.avg}</div>
                      <div className="text-xs text-slate-600 mt-0.5">min {stats.min} · max {stats.max} · p95 {stats.p95}</div>
                    </>
                  ) : (
                    <div className="mt-1 text-slate-600">—</div>
                  )}
                </div>
              );
            })}
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            {CHARTS.map((chart) => (
              <section key={chart.key} className="rounded-lg border border-border bg-panel p-4" style={{ height: 280 }}>
                <h2 className="mb-3 text-sm font-medium text-slate-200">{chart.label} ({chart.unit})</h2>
                {chart.key === "packet_loss_pct" && chartData.length > 0 && chartData.every((point) => point.packet_loss_pct == null) && (
                  <p className="mb-2 text-xs text-slate-500">
                    ICMP replies were unavailable for these runs, so packet loss could not be measured.
                  </p>
                )}
                <ResponsiveContainer width="100%" height="90%">
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#232a37" />
                    <XAxis
                      dataKey="timestamp"
                      tick={{ fill: "#64748b", fontSize: 10 }}
                      hide={chartData.length > 12}
                      tickFormatter={(value) => new Date(String(value)).toLocaleDateString()}
                    />
                    <YAxis
                      tick={{ fill: "#64748b", fontSize: 11 }}
                      domain={chart.key === "health_score" ? [0, 100] : [0, "auto"]}
                      width={42}
                    />
                    <Tooltip
                      labelFormatter={(value) => new Date(String(value)).toLocaleString()}
                      contentStyle={{ background: "#161b25", border: "1px solid #232a37", fontSize: 12 }}
                      formatter={(value, _name, item) => [
                        `${value ?? "—"} ${chart.unit} · ${item.payload.simulated ? "Demo" : "Real"}`,
                        chart.label,
                      ]}
                    />
                    <Line
                      type="monotone"
                      dataKey={chart.key}
                      stroke={chart.color}
                      dot={chartData.length <= 20}
                      connectNulls={false}
                      name={chart.label}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </section>
            ))}
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
