import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Stethoscope,
  Gauge,
  Activity,
  Network,
  Route as RouteIcon,
  Cable,
  ScanLine,
  LineChart,
  Bell,
  FileText,
  Settings,
  LogOut,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";

const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/diagnostics", label: "Diagnostics", icon: Stethoscope },
  { to: "/speed-test", label: "Speed Test", icon: Gauge },
  { to: "/live-monitor", label: "Live Monitor", icon: Activity },
  { to: "/network-map", label: "Network Map", icon: Network },
  { to: "/traceroute", label: "Traceroute", icon: RouteIcon },
  { to: "/connections", label: "Connections", icon: Cable },
  { to: "/packet-analyzer", label: "Packet Analyzer", icon: ScanLine },
  { to: "/analytics", label: "Analytics", icon: LineChart },
  { to: "/alerts", label: "Alerts", icon: Bell },
  { to: "/reports", label: "Reports", icon: FileText },
  { to: "/settings", label: "Settings", icon: Settings },
];

export default function Sidebar() {
  const { user, logout } = useAuth();

  return (
    <aside className="hidden md:flex md:w-60 md:flex-col border-r border-border bg-panel">
      <div className="px-5 py-5 border-b border-border">
        <div className="text-sm font-mono text-healthy tracking-wide">NETDOCTOR</div>
        <div className="text-xs text-slate-500 mt-0.5">Network Diagnostics Platform</div>
      </div>

      <nav className="flex-1 overflow-y-auto py-3">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-5 py-2.5 text-sm transition-colors ${
                isActive
                  ? "bg-panel2 text-slate-100 border-r-2 border-healthy"
                  : "text-slate-400 hover:text-slate-200 hover:bg-panel2"
              }`
            }
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-border px-5 py-4">
        <div className="text-xs text-slate-500 truncate">{user?.email}</div>
        <button
          onClick={logout}
          className="mt-2 flex items-center gap-2 text-xs text-slate-400 hover:text-critical transition-colors"
        >
          <LogOut size={14} /> Log out
        </button>
      </div>
    </aside>
  );
}
