import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Dashboard from "./pages/Dashboard";
import Diagnostics from "./pages/Diagnostics";
import SpeedTest from "./pages/SpeedTest";
import LiveMonitor from "./pages/LiveMonitor";
import NetworkMap from "./pages/NetworkMap";
import Traceroute from "./pages/Traceroute";
import Connections from "./pages/Connections";
import PacketAnalyzer from "./pages/PacketAnalyzer";
import Analytics from "./pages/Analytics";
import Alerts from "./pages/Alerts";
import Reports from "./pages/Reports";
import Settings from "./pages/Settings";

function protect(element: JSX.Element) {
  return <ProtectedRoute>{element}</ProtectedRoute>;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/dashboard" element={protect(<Dashboard />)} />
          <Route path="/diagnostics" element={protect(<Diagnostics />)} />
          <Route path="/speed-test" element={protect(<SpeedTest />)} />
          <Route path="/live-monitor" element={protect(<LiveMonitor />)} />
          <Route path="/network-map" element={protect(<NetworkMap />)} />
          <Route path="/traceroute" element={protect(<Traceroute />)} />
          <Route path="/connections" element={protect(<Connections />)} />
          <Route path="/packet-analyzer" element={protect(<PacketAnalyzer />)} />
          <Route path="/analytics" element={protect(<Analytics />)} />
          <Route path="/alerts" element={protect(<Alerts />)} />
          <Route path="/reports" element={protect(<Reports />)} />
          <Route path="/settings" element={protect(<Settings />)} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
