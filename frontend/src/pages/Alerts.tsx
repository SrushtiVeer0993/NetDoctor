import { useEffect, useState } from "react";
import { Bell, Check } from "lucide-react";
import DashboardLayout from "../layouts/DashboardLayout";
import { api } from "../services/api";
import type { AlertEvent } from "../types";

function errorMessage(error: any) {
  const detail = error?.response?.data?.detail;
  return typeof detail === "string" ? detail : error?.message || "Something went wrong.";
}

export default function Alerts() {
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<AlertEvent[]>("/api/alerts");
      setAlerts(res.data);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  async function acknowledge(id: number) {
    setBusyId(id);
    setError(null);
    try {
      await api.post(`/api/alerts/${id}/acknowledge`);
      setAlerts((prev) => prev.map((alert) => (alert.id === id ? { ...alert, acknowledged: true } : alert)));
    } catch (err) {
      setError(`Could not acknowledge this alert: ${errorMessage(err)}`);
    } finally {
      setBusyId(null);
    }
  }

  useEffect(() => { void load(); }, []);

  return (
    <DashboardLayout>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-slate-100">Alerts</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Fired after consecutive threshold breaches during Live Monitoring — configurable in Settings
        </p>
      </div>

      {error && (
        <div role="alert" className="mb-4 rounded-lg border border-red-900 bg-red-950/30 p-4 text-sm text-red-300">
          {error}
          {!loading && <button onClick={() => void load()} className="ml-3 underline">Retry</button>}
        </div>
      )}
      {loading && <div role="status" className="text-sm text-slate-500">Loading alerts…</div>}

      {!loading && !error && alerts.length === 0 && (
        <div className="rounded-lg border border-border bg-panel p-8 text-center text-slate-500">
          No alerts yet. Alerts fire during Live Monitoring after a metric exceeds its threshold for the configured number of consecutive checks.
        </div>
      )}

      <div className="space-y-3">
        {alerts.map((alert) => (
          <div key={alert.id} className={`rounded-lg border p-4 flex items-start justify-between gap-4 ${alert.acknowledged ? "border-border bg-panel opacity-60" : "border-warning/30 bg-warning/10"}`}>
            <div className="flex gap-3 min-w-0">
              <Bell size={16} className={`mt-0.5 shrink-0 ${alert.acknowledged ? "text-slate-600" : "text-warning"}`} />
              <div className="min-w-0">
                <div className="text-sm text-slate-200">{alert.message}</div>
                <div className="text-xs text-slate-500 mt-1">{new Date(alert.triggered_at).toLocaleString()}</div>
              </div>
            </div>
            {!alert.acknowledged && (
              <button
                onClick={() => void acknowledge(alert.id)}
                disabled={busyId === alert.id}
                className="flex shrink-0 items-center gap-1 text-xs text-slate-400 hover:text-healthy disabled:opacity-50"
              >
                <Check size={14} /> {busyId === alert.id ? "Saving…" : "Acknowledge"}
              </button>
            )}
          </div>
        ))}
      </div>
    </DashboardLayout>
  );
}
