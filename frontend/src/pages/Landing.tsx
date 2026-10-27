import { Link } from "react-router-dom";
import {
  Stethoscope,
  Activity,
  Gauge,
  Route as RouteIcon,
  Network,
  ScanLine,
  LineChart,
  FileText,
} from "lucide-react";

const FEATURES = [
  { icon: Stethoscope, title: "Network Diagnostics", desc: "Gateway, internet, latency, packet loss, DNS and HTTP tests in one run." },
  { icon: Activity, title: "Live Monitoring", desc: "Streamed latency, packet loss and DNS checks over WebSockets." },
  { icon: Gauge, title: "Speed Test", desc: "Download/upload throughput with clearly labeled methodology." },
  { icon: RouteIcon, title: "Traceroute", desc: "Hop-by-hop path visualization to any destination." },
  { icon: Network, title: "Network Map", desc: "LAN topology via ARP and controlled local discovery." },
  { icon: ScanLine, title: "Packet Analyzer", desc: "Educational packet capture and protocol breakdown." },
  { icon: LineChart, title: "Analytics", desc: "Historical trends, baselines and anomaly detection." },
  { icon: FileText, title: "Reports", desc: "Exportable PDF / CSV / JSON diagnostic reports." },
];

const CONCEPTS = ["IP", "ICMP", "DNS", "HTTP", "ARP", "TCP/UDP", "Routing", "Packet Analysis"];

export default function Landing() {
  return (
    <div className="min-h-screen bg-bg text-slate-200">
      <header className="border-b border-border">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <span className="font-mono text-healthy tracking-wide">NETDOCTOR</span>
          <div className="flex gap-3">
            <Link to="/login" className="text-sm text-slate-400 hover:text-slate-200 px-3 py-1.5">
              Log in
            </Link>
            <Link
              to="/register"
              className="text-sm bg-healthy text-black font-medium px-3 py-1.5 rounded-md hover:opacity-90"
            >
              Get started
            </Link>
          </div>
        </div>
      </header>

      <section className="max-w-4xl mx-auto px-6 pt-20 pb-14 text-center">
        <h1 className="text-4xl md:text-5xl font-semibold leading-tight">
          Understand Your Network.
          <br />
          Before You Blame Your Internet.
        </h1>
        <p className="mt-5 text-slate-400 text-lg">
          Diagnose, monitor and analyze your network from a single platform.
        </p>
        <div className="mt-8 flex justify-center gap-4">
          <Link
            to="/register"
            className="bg-healthy text-black font-medium px-5 py-2.5 rounded-md hover:opacity-90"
          >
            Run Network Test
          </Link>
          <Link
            to="/login"
            className="border border-border px-5 py-2.5 rounded-md text-slate-300 hover:bg-panel"
          >
            Explore Dashboard
          </Link>
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-6 py-10">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
          {FEATURES.map(({ icon: Icon, title, desc }) => (
            <div key={title} className="rounded-lg border border-border bg-panel p-5">
              <Icon size={20} className="text-healthy" />
              <div className="mt-3 font-medium text-slate-100">{title}</div>
              <div className="mt-1 text-sm text-slate-500">{desc}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="max-w-4xl mx-auto px-6 py-14 text-center">
        <div className="flex flex-wrap items-center justify-center gap-3 text-sm font-mono text-slate-400">
          <span className="px-3 py-1.5 rounded-md border border-border">Measure</span>
          <span>→</span>
          <span className="px-3 py-1.5 rounded-md border border-border">Analyze</span>
          <span>→</span>
          <span className="px-3 py-1.5 rounded-md border border-border">Diagnose</span>
          <span>→</span>
          <span className="px-3 py-1.5 rounded-md border border-border">Recommend</span>
        </div>
      </section>

      <section className="max-w-4xl mx-auto px-6 pb-20 text-center">
        <div className="text-xs uppercase tracking-wide text-slate-600 mb-4">
          Computer Networks concepts demonstrated
        </div>
        <div className="flex flex-wrap justify-center gap-2">
          {CONCEPTS.map((c) => (
            <span key={c} className="text-xs font-mono px-2.5 py-1 rounded border border-border text-slate-400">
              {c}
            </span>
          ))}
        </div>
      </section>
    </div>
  );
}
