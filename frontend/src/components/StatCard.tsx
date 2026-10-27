import type { LucideIcon } from "lucide-react";

interface Props {
  label: string;
  value: string;
  sub?: string;
  tone?: "healthy" | "warning" | "critical" | "info" | "neutral";
  icon?: LucideIcon;
}

const TONE_CLASSES: Record<string, string> = {
  healthy: "text-healthy",
  warning: "text-warning",
  critical: "text-critical",
  info: "text-info",
  neutral: "text-slate-200",
};

export default function StatCard({ label, value, sub, tone = "neutral", icon: Icon }: Props) {
  return (
    <div className="rounded-lg border border-border bg-panel px-4 py-3.5 transition-colors hover:border-slate-700">
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs text-slate-500 uppercase tracking-wide">{label}</div>
        {Icon && <Icon size={16} className={TONE_CLASSES[tone]} aria-hidden="true" />}
      </div>
      <div className={`mt-2 text-xl font-mono-num font-semibold ${TONE_CLASSES[tone]}`}>
        {value}
      </div>
      {sub && <div className="mt-1 text-xs leading-4 text-slate-500">{sub}</div>}
    </div>
  );
}
