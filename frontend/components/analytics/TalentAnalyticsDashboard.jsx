import { BarChart3, BriefcaseBusiness, Gauge, UsersRound } from "lucide-react";

export function TalentAnalyticsDashboard({ candidates = [] }) {
  const averageScore = Math.round(candidates.reduce((sum, item) => sum + (item.final_score || 0), 0) / Math.max(candidates.length, 1));
  const cards = [
    ["Candidate quality", `${averageScore}%`, "Average AI fit score", Gauge],
    ["Active candidates", candidates.length, "In current workspace", UsersRound],
    ["Open roles", 12, "Across departments", BriefcaseBusiness],
    ["Bottleneck", "HM Review", "Largest stage concentration", BarChart3]
  ];

  return (
    <section className="grid gap-3 lg:grid-cols-4">
      {cards.map(([label, value, caption, Icon]) => (
        <div key={label} className="rounded-md border border-ats-line bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <div className="text-xs font-semibold uppercase tracking-normal text-ats-muted">{label}</div>
            <Icon size={18} className="text-ats-muted" />
          </div>
          <div className="mt-3 text-2xl font-semibold text-ats-ink">{value}</div>
          <div className="mt-1 text-xs text-ats-muted">{caption}</div>
        </div>
      ))}
    </section>
  );
}
