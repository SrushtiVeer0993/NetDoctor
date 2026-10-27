interface Props {
  score: number;
}

function toneFor(score: number) {
  if (score >= 80) return { color: "#22c55e", label: "Healthy" };
  if (score >= 50) return { color: "#eab308", label: "Degraded" };
  return { color: "#ef4444", label: "Problem" };
}

export default function HealthScoreGauge({ score }: Props) {
  const { color, label } = toneFor(score);
  const circumference = 2 * Math.PI * 54;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-border bg-panel px-6 py-6">
      <svg width="140" height="140" viewBox="0 0 140 140">
        <circle cx="70" cy="70" r="54" fill="none" stroke="#232a37" strokeWidth="10" />
        <circle
          cx="70"
          cy="70"
          r="54"
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform="rotate(-90 70 70)"
        />
        <text x="70" y="66" textAnchor="middle" fontSize="28" fontWeight="700" fill="#e2e8f0">
          {score}
        </text>
        <text x="70" y="86" textAnchor="middle" fontSize="11" fill="#64748b">
          / 100
        </text>
      </svg>
      <div className="mt-2 text-sm font-medium" style={{ color }}>
        {label}
      </div>
      <div className="mt-1 text-[11px] text-slate-600 text-center max-w-[160px]">
        Application-defined diagnostic indicator, not an industry-standard metric
      </div>
    </div>
  );
}
