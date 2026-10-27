export interface User {
  id: number;
  email: string;
  full_name: string | null;
}

export interface GatewayResult {
  reachable: boolean | null;
  gateway_ip: string | null;
  avg_ms: number | null;
  icmp_unavailable: boolean;
  source?: string;
  interface_name?: string | null;
  interface_type?: string | null;
  detail?: string;
  error_type?: string | null;
}

export interface InternetResult {
  reachable: boolean | null;
  target: string;
  avg_ms: number | null;
  method?: string;
  icmp_reachable?: boolean;
  icmp_unavailable?: boolean;
  source?: string;
  detail?: string;
  icmp_error_type?: string | null;
  icmp_detail?: string | null;
}

export interface LatencyResult {
  target: string;
  min_ms: number | null;
  max_ms: number | null;
  avg_ms: number | null;
  jitter_ms: number | null;
  sent: number;
  received: number;
  samples: number[];
  source?: string;
  error_type?: string | null;
  error?: string | null;
}

export interface PacketLossResult {
  target: string;
  sent: number;
  received: number;
  loss_pct: number;
  icmp_unavailable?: boolean;
  source?: string;
  error_type?: string | null;
  error?: string | null;
}

export interface DnsResult {
  domain: string;
  resolved_ip: string | null;
  response_ms: number | null;
  success: boolean;
  error?: string;
  source?: string;
}

export interface WebsiteResult {
  url: string;
  reachable: boolean;
  status_code: number | null;
  successful_request: boolean;
  response_ms: number | null;
  http_category?: "success" | "redirect" | "client_error" | "server_error" | "other" | null;
  error_type?: string;
  error?: string;
  source?: string;
}

export interface Finding {
  code?: string;
  severity: "critical" | "warning" | "info" | "healthy";
  confidence: "low" | "medium" | "high";
  evidence: string;
  text: string;
  recommendations?: string[];
}

export interface DeviceDiscoveryResult {
  supported: boolean | null;
  status?: "skipped" | "completed" | "success" | "empty" | "partial" | "unsupported" | "permission_denied" | "failed";
  detail?: string | null;
  scanned_hosts?: number;
  subnet?: string;
  interface_name?: string;
  source?: string;
  devices: { ip: string; mac: string | null }[];
}

export interface DiagnosisResultJson {
  timestamp: string;
  simulated?: boolean;
  source?: string;
  host_agent?: { available: boolean; detail: string | null };
  interface?: {
    interface_name: string | null;
    connection_type: string;
    local_ip: string | null;
    subnet: string | null;
    gateway: string | null;
    gateway_ipv6?: string | null;
  };
  gateway: GatewayResult;
  internet: InternetResult;
  latency: LatencyResult;
  packet_loss: PacketLossResult;
  dns: DnsResult;
  websites: WebsiteResult[];
  devices: DeviceDiscoveryResult;
  health_score: number;
  health_score_factors: Record<string, number>;
  findings: Finding[];
  recommendations: string[];
}

export interface DiagnosisSummary {
  id: number;
  created_at: string;
  health_score: number;
  gateway_reachable: boolean | null;
  internet_reachable: boolean | null;
  latency_avg_ms: number | null;
  packet_loss_pct: number | null;
  dns_response_ms: number | null;
  top_finding: string | null;
}

export interface DiagnosisResult extends DiagnosisSummary {
  result_json: DiagnosisResultJson;
}

export interface DashboardData {
  has_data: boolean;
  latest: (DiagnosisSummary & {
    recommendations: string[];
    devices_discovered: number;
    device_discovery_status: string;
    simulated: boolean;
    source?: string;
  }) | null;
  recent_tests: {
    id: number;
    created_at: string;
    health_score: number;
    latency_avg_ms: number | null;
    packet_loss_pct: number | null;
    simulated: boolean;
    source?: string;
  }[];
}

export interface InterfaceSummary {
  simulated: boolean;
  source?: string;
  gateway_ipv6?: string | null;
  host_agent?: { available: boolean; detail: string | null } | null;
  interface_name: string | null;
  connection_type: string;
  local_ip: string | null;
  subnet: string | null;
  gateway: string | null;
  dns_servers: string[];
  mac_address: string | null;
  ssid: string | null;
  signal_dbm: number | null;
  frequency_mhz: number | null;
  link_speed_mbps: number | null;
}

export interface ConnectionRow {
  protocol: string;
  local_ip: string;
  local_port: string | null;
  remote_ip: string | null;
  remote_port: string | null;
  state: string;
}

export interface TracerouteHop {
  hop: number;
  ip: string | null;
  hostname: string | null;
  latency_ms: number | null;
  status: string;
}

export interface TracerouteResult {
  supported: boolean;
  simulated: boolean;
  target: string;
  hops: TracerouteHop[];
  destination_reached?: boolean;
  error?: string;
  run_id?: number;
}

export interface DiscoveredDevice {
  id?: number;
  ip: string;
  subnet?: string | null;
  mac: string | null;
  hostname?: string | null;
  status?: "responsive" | "neighbor_cache" | "not_seen" | string;
  last_seen?: string;
}

export interface SpeedTestResult {
  simulated: boolean;
  methodology: string;
  source?: string;
  download: { success: boolean; mbps: number | null; bytes?: number; seconds?: number; samples_mbps?: number[]; error?: string };
  upload: { success: boolean; mbps: number | null; bytes?: number; seconds?: number; samples_mbps?: number[]; error?: string };
  latency_ms: number | null;
  jitter_ms: number | null;
  id?: number;
  created_at?: string;
}

export interface MonitorMessage {
  error?: string;
  timestamp: string;
  latency_ms: number | null;
  packet_loss: number | null;
  dns_ms: number | null;
  dns_success?: boolean;
  internet: boolean | null;
  simulated: boolean;
  source?: string;
  icmp_unavailable?: boolean;
  alerts?: { metric: string; message: string }[];
}

export interface AlertEvent {
  id: number;
  triggered_at: string;
  metric: string;
  current_value: number | null;
  baseline_value: number | null;
  message: string;
  acknowledged: boolean;
}

export interface PacketSummary {
  index: number;
  timestamp: string;
  protocol: string;
  source: string | null;
  destination: string | null;
  source_port: number | null;
  destination_port: number | null;
  length: number;
  parsed: Record<string, Record<string, string | number>>;
}

export interface AnalyticsStats {
  avg: number; min: number; max: number; p95: number;
}

export interface AnalyticsData {
  has_data: boolean;
  range: string;
  stats_source?: "real" | "simulated" | "mixed";
  stats: Record<string, AnalyticsStats | null>;
  series: {
    timestamp: string; health_score: number; latency_avg_ms: number | null;
    packet_loss_pct: number | null; dns_response_ms: number | null; simulated: boolean;
  }[];
}

export interface UserSettingsData {
  monitoring_interval_seconds: number;
  default_ping_target: string;
  default_dns_domain: string;
  demo_mode: boolean;
  latency_alert_ms: number;
  packet_loss_alert_pct: number;
  alert_consecutive_checks: number;
}
