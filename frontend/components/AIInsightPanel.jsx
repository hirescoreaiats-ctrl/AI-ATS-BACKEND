import { Sparkles } from "lucide-react";

export function AIInsightPanel({ summary }) {
  return (
    <aside className="rounded-md border border-ats-line bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2">
        <Sparkles size={18} className="text-ats-brand" />
        <h2 className="text-sm font-semibold text-ats-ink">AI Recruiter Copilot</h2>
      </div>
      <div className="mt-4 grid gap-3 text-sm">
        <div>
          <div className="text-xs font-medium uppercase tracking-normal text-ats-muted">Pipeline health</div>
          <div className="mt-1 font-semibold text-ats-ink">{summary.pipeline_health || "needs review"}</div>
        </div>
        <div>
          <div className="text-xs font-medium uppercase tracking-normal text-ats-muted">Next actions</div>
          <ul className="mt-2 space-y-2 text-ats-muted">
            {(summary.next_best_actions || []).map((action) => (
              <li key={action}>{action}</li>
            ))}
          </ul>
        </div>
      </div>
    </aside>
  );
}
