import { FormEvent, useEffect, useState } from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import { api } from "../services/api";
import type { UserSettingsData } from "../types";

function errorMessage(error: any) {
  const detail = error?.response?.data?.detail;
  return typeof detail === "string" ? detail : error?.message || "Something went wrong.";
}

export default function Settings() {
  const [form, setForm] = useState<UserSettingsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<UserSettingsData>("/api/settings");
      setForm(res.data);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!form) return;
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      const res = await api.put<UserSettingsData>("/api/settings", form);
      setForm(res.data);
      setSaved(true);
    } catch (err) {
      setError(`Settings could not be saved: ${errorMessage(err)}`);
    } finally {
      setSaving(false);
    }
  }

  function field<K extends keyof UserSettingsData>(key: K, value: UserSettingsData[K]) {
    setSaved(false);
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));
  }

  if (loading || !form) {
    return (
      <DashboardLayout>
        {loading ? (
          <div role="status" className="text-sm text-slate-500">Loading settings…</div>
        ) : (
          <div role="alert" className="rounded-lg border border-red-900 bg-red-950/30 p-4 text-sm text-red-300">
            Could not load settings: {error}
            <button onClick={() => void load()} className="ml-3 underline">Retry</button>
          </div>
        )}
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-slate-100">Settings</h1>
        <p className="text-sm text-slate-500 mt-0.5">Default diagnostic targets, alert thresholds, and demo mode</p>
      </div>

      {error && (
        <div role="alert" className="mb-4 rounded-lg border border-red-900 bg-red-950/30 p-4 text-sm text-red-300">{error}</div>
      )}

      <form onSubmit={handleSubmit} className="max-w-lg space-y-5">
        <div className="rounded-lg border border-border bg-panel p-5 space-y-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-sm font-medium text-slate-200">Demo mode</div>
              <div className="text-xs text-slate-500 mt-0.5">
                Use clearly labeled simulated results instead of real measurements.
              </div>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={form.demo_mode}
              aria-label="Demo mode"
              onClick={() => field("demo_mode", !form.demo_mode)}
              className={`w-11 h-6 shrink-0 rounded-full transition-colors relative ${form.demo_mode ? "bg-healthy" : "bg-border"}`}
            >
              <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition-transform ${form.demo_mode ? "translate-x-5" : "translate-x-0.5"}`} />
            </button>
          </div>
        </div>

        <div className="rounded-lg border border-border bg-panel p-5 space-y-4">
          <div className="text-sm font-medium text-slate-200">Default targets</div>
          <div>
            <label htmlFor="ping-target" className="text-xs text-slate-500">Ping / monitoring target</label>
            <input
              id="ping-target"
              type="text"
              autoComplete="off"
              required
              maxLength={253}
              value={form.default_ping_target}
              onChange={(event) => field("default_ping_target", event.target.value)}
              className="mt-1 w-full rounded-md bg-panel2 border border-border px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-healthy"
            />
            <p className="mt-1 text-xs text-slate-600">Enter a hostname or IP address, not a URL.</p>
          </div>
          <div>
            <label htmlFor="dns-domain" className="text-xs text-slate-500">DNS test domain</label>
            <input
              id="dns-domain"
              type="text"
              autoComplete="off"
              required
              maxLength={253}
              value={form.default_dns_domain}
              onChange={(event) => field("default_dns_domain", event.target.value)}
              className="mt-1 w-full rounded-md bg-panel2 border border-border px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-healthy"
            />
            <p className="mt-1 text-xs text-slate-600">Used as the DNS lookup target in Full Diagnostics.</p>
          </div>
          <div>
            <label htmlFor="monitor-interval" className="text-xs text-slate-500">Monitoring interval (seconds)</label>
            <input
              id="monitor-interval"
              type="number"
              min={1}
              max={3600}
              step={1}
              required
              value={form.monitoring_interval_seconds}
              onChange={(event) => field("monitoring_interval_seconds", Number(event.target.value))}
              className="mt-1 w-full rounded-md bg-panel2 border border-border px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-healthy"
            />
          </div>
        </div>

        <div className="rounded-lg border border-border bg-panel p-5 space-y-4">
          <div className="text-sm font-medium text-slate-200">Alert thresholds</div>
          <div>
            <label htmlFor="latency-threshold" className="text-xs text-slate-500">Latency alert (ms)</label>
            <input
              id="latency-threshold"
              type="number"
              min={0.1}
              max={10000}
              step="any"
              required
              value={form.latency_alert_ms}
              onChange={(event) => field("latency_alert_ms", Number(event.target.value))}
              className="mt-1 w-full rounded-md bg-panel2 border border-border px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-healthy"
            />
          </div>
          <div>
            <label htmlFor="loss-threshold" className="text-xs text-slate-500">Packet loss alert (%)</label>
            <input
              id="loss-threshold"
              type="number"
              min={0}
              max={100}
              step="any"
              required
              value={form.packet_loss_alert_pct}
              onChange={(event) => field("packet_loss_alert_pct", Number(event.target.value))}
              className="mt-1 w-full rounded-md bg-panel2 border border-border px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-healthy"
            />
          </div>
          <div>
            <label htmlFor="alert-count" className="text-xs text-slate-500">Consecutive checks before alert fires</label>
            <input
              id="alert-count"
              type="number"
              min={1}
              max={100}
              step={1}
              required
              value={form.alert_consecutive_checks}
              onChange={(event) => field("alert_consecutive_checks", Number(event.target.value))}
              className="mt-1 w-full rounded-md bg-panel2 border border-border px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-healthy"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={saving}
          className="bg-healthy text-black font-medium text-sm px-4 py-2 rounded-md hover:opacity-90 disabled:opacity-50"
        >
          {saving ? "Saving…" : saved ? "Saved ✓" : "Save settings"}
        </button>
      </form>
    </DashboardLayout>
  );
}
