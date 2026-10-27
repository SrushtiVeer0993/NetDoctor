import { useEffect, useState } from "react";
import { Play, Square } from "lucide-react";
import DashboardLayout from "../layouts/DashboardLayout";
import DemoBadge from "../components/DemoBadge";
import { api } from "../services/api";
import type { PacketSummary } from "../types";

const FILTERS = ["ALL", "TCP", "UDP", "ICMP", "DNS"];

export default function PacketAnalyzer() {
  const [captureId, setCaptureId] = useState<string | null>(null);
  const [simulated, setSimulated] = useState(false);
  const [supported, setSupported] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [packets, setPackets] = useState<PacketSummary[]>([]);
  const [filter, setFilter] = useState("ALL");
  const [selected, setSelected] = useState<PacketSummary | null>(null);
  const [running, setRunning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [captureSource, setCaptureSource] = useState<string | null>(null);
  const [captureStatus, setCaptureStatus] = useState<string | null>(null);

  async function start() {
    setError(null);
    setBusy(true);
    setPackets([]);
    setSelected(null);
    try {
      const res = await api.post("/api/packet-capture/start", { duration_seconds: 20, max_packets: 200 });
      if (!res.data.supported) {
        setSupported(false);
        setError(res.data.error || "Packet capture unavailable on this system.");
        return;
      }
      setSupported(true);
      setCaptureId(res.data.capture_id);
      setCaptureSource(res.data.source ?? (res.data.simulated ? "simulated" : "backend_runtime"));
      setSimulated(!!res.data.simulated);
      setCaptureStatus("running");
      setRunning(true);
    } catch (err: any) {
      setRunning(false);
      setError(err?.response?.data?.detail || "Could not start packet capture.");
    } finally {
      setBusy(false);
    }
  }

  async function stop() {
    if (!captureId) return;
    setBusy(true);
    try {
      const res = await api.post(`/api/packet-capture/stop?capture_id=${encodeURIComponent(captureId)}`);
      if (!res.data.stopped) throw new Error(res.data.error || "Could not stop capture.");
      setRunning(false);
      setCaptureStatus("stopped");
      await refresh(captureId, filter);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || "Could not stop packet capture.");
    } finally {
      setBusy(false);
    }
  }

  async function refresh(id = captureId, protocol = filter) {
    if (!id) return;
    try {
      const res = await api.get(`/api/packet-capture/packets/${encodeURIComponent(id)}`, { params: { protocol } });
      const nextPackets: PacketSummary[] = res.data.packets || [];
      setPackets(nextPackets);
      setSelected((current) => current ? nextPackets.find((packet) => packet.index === current.index) ?? null : null);
      if (id !== "demo") {
        const status = await api.get(`/api/packet-capture/status/${encodeURIComponent(id)}`);
        if (status.data.error) throw new Error(status.data.error);
        setCaptureStatus(status.data.status);
        if (status.data.status === "stopped") setRunning(false);
      }
      setError(null);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || "Could not refresh captured packets.");
    }
  }

  useEffect(() => {
    if (!running || !captureId || captureId === "demo") return;
    const timer = window.setInterval(() => { void refresh(captureId, filter); }, 1000);
    return () => window.clearInterval(timer);
  }, [captureId, filter, running]);

  return (
    <DashboardLayout>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-slate-100 flex items-center">
            Packet Analyzer <DemoBadge show={simulated} />
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Backend-only capture — requires administrator/root privileges. Educational protocol breakdown.
          </p>
        </div>
        {!running ? (
          <button onClick={start} disabled={busy} className="flex items-center gap-2 bg-healthy text-black font-medium text-sm px-4 py-2 rounded-md hover:opacity-90 disabled:opacity-50">
            <Play size={15} /> Start capture
          </button>
        ) : (
          <button onClick={stop} disabled={busy} className="flex items-center gap-2 bg-critical text-white font-medium text-sm px-4 py-2 rounded-md hover:opacity-90 disabled:opacity-50">
            <Square size={15} /> Stop &amp; view
          </button>
        )}
      </div>

      {error && (
        <div role="alert" className="text-sm text-warning bg-warning/10 border border-warning/30 rounded-md px-3 py-2 mb-5">
          {error}
        </div>
      )}

      {captureSource === "docker_container" && (
        <div role="status" className="text-sm text-warning bg-warning/10 border border-warning/30 rounded-md px-3 py-2 mb-5">
          Docker capture observes traffic visible to the container; it is not a full capture of the Windows laptop.
        </div>
      )}

      {supported && captureId && (
        <>
          <div className="text-xs text-slate-500 mb-3">
            Capture {captureStatus ?? (running ? "running" : "stopped")} | {packets.length} packet(s) currently shown
            {captureSource && <span className="ml-2 text-slate-400">Source: {captureSource}</span>}
          </div>
          <div className="flex gap-2 mb-4">
            {FILTERS.map((f) => (
              <button
                key={f}
                onClick={() => { setFilter(f); void refresh(captureId, f); }}
                className={`text-xs px-3 py-1.5 rounded-md border ${filter === f ? "border-healthy text-healthy" : "border-border text-slate-500"}`}
              >
                {f}
              </button>
            ))}
            <button onClick={() => void refresh()} className="text-xs px-3 py-1.5 rounded-md border border-border text-slate-400 ml-auto">
              Refresh
            </button>
          </div>

          <div className="grid grid-cols-3 gap-5">
            <div className="col-span-2 rounded-lg border border-border bg-panel p-4 max-h-[500px] overflow-y-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-slate-600 uppercase sticky top-0 bg-panel">
                    <th className="pb-2 font-normal">Time</th>
                    <th className="pb-2 font-normal">Source</th>
                    <th className="pb-2 font-normal">Destination</th>
                    <th className="pb-2 font-normal">Proto</th>
                    <th className="pb-2 font-normal">Length</th>
                  </tr>
                </thead>
                <tbody>
                  {packets.map((p) => (
                    <tr
                      key={p.index}
                      onClick={() => setSelected(p)}
                      className={`border-t border-border cursor-pointer hover:bg-panel2 ${selected?.index === p.index ? "bg-panel2" : ""}`}
                    >
                      <td className="py-1.5 text-slate-500 font-mono text-xs">{new Date(p.timestamp).toLocaleTimeString()}</td>
                      <td className="py-1.5 text-slate-300 font-mono text-xs">{p.source ?? "—"}{p.source_port ? `:${p.source_port}` : ""}</td>
                      <td className="py-1.5 text-slate-300 font-mono text-xs">{p.destination ?? "—"}{p.destination_port ? `:${p.destination_port}` : ""}</td>
                      <td className="py-1.5 text-info text-xs">{p.protocol}</td>
                      <td className="py-1.5 text-slate-500 font-mono-num text-xs">{p.length}</td>
                    </tr>
                  ))}
                  {packets.length === 0 && (
                    <tr><td colSpan={5} className="py-6 text-center text-slate-600">No packets captured yet.</td></tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="rounded-lg border border-border bg-panel p-4">
              <div className="text-sm font-medium text-slate-200 mb-3">Packet details</div>
              {!selected && <div className="text-sm text-slate-600">Click a packet to inspect its fields.</div>}
              {selected && (
                <div className="space-y-3 text-xs font-mono">
                  {Object.entries(selected.parsed).map(([layer, fields]) => (
                    <div key={layer}>
                      <div className="text-healthy uppercase">{layer}</div>
                      {Object.entries(fields).map(([k, v]) => (
                        <div key={k} className="flex justify-between text-slate-400 pl-2">
                          <span>{k}</span><span className="text-slate-300">{String(v)}</span>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </DashboardLayout>
  );
}
