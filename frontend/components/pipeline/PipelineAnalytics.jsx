import { Activity, Clock3, MoveRight, TrendingUp } from "lucide-react";

export function PipelineAnalytics({ candidates = [] }) {
  const interviewCount = candidates.filter((candidate) => String(candidate.stage || "").includes("interview")).length;
  const offerCount = candidates.filter((candidate) => candidate.stage === "offer").length;
  const highConfidence = candidates.filter((candidate) => (candidate.confidence_score || 0) >= 75).length;
  const metrics = [
    ["In interviews", interviewCount, Clock3],
    ["Offers", offerCount, MoveRight],
    ["High confidence", highConfidence, TrendingUp],
    ["Active records", candidates.length, Activity]
  ];
  return (
    <div className="grid gap-3 md:grid-cols-4">
      {metrics.map(([label, value, Icon]) => (
        <div key={label} className="rounded-md border border-ats-line bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between text-xs font-medium uppercase tracking-normal text-ats-muted">
            {label}
            <Icon size={17} />
          </div>
          <div className="mt-3 text-2xl font-semibold text-ats-ink">{value}</div>
        </div>
      ))}
    </div>
  );
}
