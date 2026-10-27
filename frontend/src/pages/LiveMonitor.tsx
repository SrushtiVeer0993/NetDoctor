import { useEffect, useRef, useState } from "react";
import axios from "axios";
import { Play, Square } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import DashboardLayout from "../layouts/DashboardLayout";
import DemoBadge from "../components/DemoBadge";
import { api, wsBaseUrl } from "../services/api";
import type { MonitorMessage } from "../types";

const MAX_POINTS = 60;

export default function LiveMonitor() {
  const [status, setStatus] = useState<"idle" | "connecting" | "live">("idle");
  const [points, setPoints] = useState<{ t: string; latency: number | null; loss: number | null }[]>([]);
  const [latest, setLatest] = useState<MonitorMessage | null>(null);
  const [alertMsgs, setAlertMsgs] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [simulated, setSimulated] = useState(false);
  const [intervalSeconds, setIntervalSeconds] = useState<number | null>(null);
  const [measurementSource, setMeasurementSource] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const sessionIdRef = useRef<number | null>(null);
  const startInProgress = useRef(false);

  useEffect(() => () => {
    startInProgress.current = false;
    wsRef.current?.close();
    if (sessionIdRef.current !== null) {
      void api.post(`/api/monitoring/stop?session_id=${sessionIdRef.current}`);
    }
  }, []);

  async function start() {
    if (startInProgress.current) return;
    startInProgress.current = true;
    setStatus("connecting");
    setPoints([]);
    setAlertMsgs([]);
    setError(null);
    try {
      const res = await api.post("/api/monitoring/start");
      const sessionId: number = res.data.session_id;
      sessionIdRef.current = sessionId;
      setSimulated(!!res.data.simulated);
      setIntervalSeconds(res.data.interval_seconds);
      setMeasurementSource(res.data.source);

      if (!startInProgress.current) {
        await api.post(`/api/monitoring/stop?session_id=${sessionId}`);
        sessionIdRef.current = null;
        return;
      }

      const token = localStorage.getItem("netdoctor_token");
      if (!token) throw new Error("Authentication token is missing.");
      const ws = new WebSocket(`${wsBaseUrl()}/ws/monitor?session_id=${sessionId}&token=${encodeURIComponent(token)}`);
      wsRef.current = ws;

      ws.onopen = () => setStatus("live");
      ws.onmessage = (evt) => {
        const data: MonitorMessage = JSON.parse(evt.data);
        if (data.error) {
          setError(data.error);
          return;
        }
        setLatest(data);
        setSimulated(data.simulated);
        setMeasurementSource(data.source ?? null);
        setPoints((prev) => {
          const next = [...prev, { t: new Date(data.timestamp).toLocaleTimeString(), latency: data.latency_ms, loss: data.packet_loss }];
          return next.slice(-MAX_POINTS);
        });
        if (data.alerts?.length) {
          setAlertMsgs((prev) => [...data.alerts!.map((a) => a.message), ...prev].slice(0, 10));
        }
      };
      ws.onerror = () => setError("The monitoring WebSocket connection failed.");
      ws.onclose = () => {
        if (wsRef.current === ws) {
          wsRef.current = null;
          setStatus("idle");
        }
      };
    } catch (err: unknown) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setError(typeof detail === "string" ? detail : err instanceof Error ? err.message : "Could not start monitoring.");
      setStatus("idle");
    } finally {
      startInProgress.current = false;
    }
  }

  async function stop() {
    startInProgress.current = false;
    wsRef.current?.close();
    wsRef.current = null;
    const sessionId = sessionIdRef.current;
    sessionIdRef.current = null;
    if (sessionId !== null) {
      try {
        await api.post(`/api/monitoring/stop?session_id=${sessionId}`);
      } catch (err: unknown) {
        const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
        setError(typeof detail === "string" ? detail : "Could not stop monitoring cleanly.");
      }
    }
    setStatus("idle");
  }

  return (
    <DashboardLayout>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-slate-100 flex items-center">
            Live Monitoring <DemoBadge show={simulated} />
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Latency and loss use the same 3 ICMP probes; internet uses TCP and DNS uses the system resolver.
            {intervalSeconds && <span className="ml-2 text-slate-400">· Target interval: {intervalSeconds}s</span>}
            {measurementSource && <span className="ml-2 text-slate-400">· Source: {measurementSource}</span>}
          </p>
        </div>
        {status === "idle" ? (
          <button onClick={start} className="flex items-center gap-2 bg-healthy text-black font-medium text-sm px-4 py-2 rounded-md hover:opacity-90">
            <Play size={15} /> Start monitoring
          </button>
        ) : (
          <button onClick={stop} className="flex items-center gap-2 bg-critical text-white font-medium text-sm px-4 py-2 rounded-md hover:opacity-90">
            <Square size={15} /> Stop
          </button>
        )}
      </div>

      {error && (
        <div className="text-sm text-critical bg-critical/10 border border-critical/30 rounded-md px-3 py-2 mb-5">
          {error}
        </div>
      )}

      <div className="flex items-center gap-2 mb-5">
        <span className={`w-2 h-2 rounded-full ${status === "live" ? "bg-healthy animate-pulse" : "bg-slate-700"}`} />
        <span className="text-sm text-slate-400">
          {status === "live" ? "LIVE · Monitoring" : status === "connecting" ? "Connecting…" : "Not monitoring"}
        </span>
      </div>

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
        <div className="rounded-lg border border-border bg-panel px-4 py-3">
          <div className="text-xs text-slate-500 uppercase">Latency</div>
          <div className="mt-1 text-2xl font-mono-num text-slate-100">{latest?.latency_ms ?? "—"} ms</div>
        </div>
        <div className="rounded-lg border border-border bg-panel px-4 py-3">
          <div className="text-xs text-slate-500 uppercase">Packet Loss</div>
          <div className="mt-1 text-2xl font-mono-num text-slate-100">
            {latest?.icmp_unavailable ? "ICMP unavailable" : latest?.packet_loss == null ? "—" : `${latest.packet_loss}%`}
          </div>
        </div>
        <div className="rounded-lg border border-border bg-panel px-4 py-3">
          <div className="text-xs text-slate-500 uppercase">Internet</div>
          <div className={`mt-1 text-2xl font-medium ${latest?.internet === true ? "text-healthy" : "text-warning"}`}>
            {latest
              ? latest.internet === null ? "Unconfirmed" : latest.internet ? "Connected" : "Unreachable"
              : "—"}
          </div>
        </div>
        <div className="rounded-lg border border-border bg-panel px-4 py-3">
          <div className="text-xs text-slate-500 uppercase">DNS response</div>
          <div className="mt-1 text-2xl font-mono-num text-slate-100">
            {!latest ? "—" : latest.dns_success === false ? "Lookup failed" : latest.dns_ms == null ? "—" : `${latest.dns_ms} ms`}
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-panel p-4 mb-6" style={{ height: 260 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points}>
            <CartesianGrid strokeDasharray="3 3" stroke="#232a37" />
            <XAxis dataKey="t" tick={{ fill: "#64748b", fontSize: 11 }} />
            <YAxis tick={{ fill: "#64748b", fontSize: 11 }} />
            <Tooltip contentStyle={{ background: "#161b25", border: "1px solid #232a37", fontSize: 12 }} />
            <Line type="monotone" dataKey="latency" stroke="#22c55e" dot={false} name="Latency (ms)" />
            <Line type="monotone" dataKey="loss" stroke="#ef4444" dot={false} name="Packet loss (%)" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {alertMsgs.length > 0 && (
        <div className="rounded-lg border border-warning/30 bg-warning/10 p-4">
          <div className="text-sm font-medium text-warning mb-2">Alerts</div>
          {alertMsgs.map((m, i) => (
            <div key={i} className="text-sm text-slate-300 py-1">⚠ {m}</div>
          ))}
        </div>
      )}
    </DashboardLayout>
  );
}
