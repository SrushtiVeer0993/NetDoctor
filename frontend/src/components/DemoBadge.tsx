export default function DemoBadge({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <span className="text-[10px] uppercase tracking-wide bg-info/20 text-info px-2 py-0.5 rounded-full ml-2">
      Demo mode — simulated
    </span>
  );
}
