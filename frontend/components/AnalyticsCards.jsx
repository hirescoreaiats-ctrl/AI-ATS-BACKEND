import { ArrowUpRight, Clock3, UserCheck, UsersRound } from "lucide-react";

const iconMap = {
  applicants: UsersRound,
  shortlisted: UserCheck,
  time: Clock3,
  conversion: ArrowUpRight
};

export function AnalyticsCards({ metrics }) {
  return (
    <section className="grid gap-3 md:grid-cols-4">
      {metrics.map((metric) => {
        const Icon = iconMap[metric.kind] || UsersRound;
        return (
          <div key={metric.label} className="rounded-md border border-ats-line bg-ats-panel p-4 shadow-sm">
            <div className="flex items-center justify-between">
              <div className="text-xs font-medium uppercase tracking-normal text-ats-muted">{metric.label}</div>
              <Icon size={18} className="text-ats-muted" />
            </div>
            <div className="mt-3 text-2xl font-semibold text-ats-ink">{metric.value}</div>
            <div className="mt-1 text-xs text-ats-muted">{metric.caption}</div>
          </div>
        );
      })}
    </section>
  );
}
