import { Clock3 } from "lucide-react";

export function CandidateTimeline({ activities = [], stageHistory = [] }) {
  const items = [
    ...stageHistory.map((item) => ({ title: `Moved to ${item.to_stage}`, body: item.reason, created_at: item.created_at })),
    ...activities.map((item) => ({ title: item.title, body: item.body, created_at: item.created_at }))
  ].slice(0, 12);

  return (
    <section className="rounded-md border border-ats-line bg-white">
      <header className="flex items-center gap-2 border-b border-ats-line px-4 py-3">
        <Clock3 size={17} className="text-ats-brand" />
        <h3 className="text-sm font-semibold text-ats-ink">Candidate Timeline</h3>
      </header>
      <div className="divide-y divide-ats-line">
        {items.map((item, index) => (
          <div key={`${item.title}-${index}`} className="px-4 py-3">
            <div className="text-sm font-medium text-ats-ink">{item.title}</div>
            <div className="mt-1 text-xs text-ats-muted">{item.body || item.created_at || "Tracked activity"}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
