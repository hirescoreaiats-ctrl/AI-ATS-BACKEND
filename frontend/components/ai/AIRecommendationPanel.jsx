import { Sparkles } from "lucide-react";
import { Badge } from "../design-system/Badge.jsx";
import { Button } from "../design-system/Button.jsx";

export function AIRecommendationPanel({ candidates = [], onCompare }) {
  const top = [...candidates].sort((a, b) => (b.final_score || 0) - (a.final_score || 0)).slice(0, 5);
  return (
    <section className="rounded-md border border-ats-line bg-white shadow-sm">
      <header className="flex items-center justify-between border-b border-ats-line px-4 py-3">
        <div className="flex items-center gap-2">
          <Sparkles size={18} className="text-ats-brand" />
          <h2 className="text-sm font-semibold text-ats-ink">AI Recommendations</h2>
        </div>
        <Button size="sm" variant="secondary" onClick={() => onCompare?.(top)}>Compare</Button>
      </header>
      <div className="divide-y divide-ats-line">
        {top.map((candidate) => (
          <div key={candidate.resume_id || candidate.id} className="px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-ats-ink">{candidate.full_name}</div>
                <div className="text-xs text-ats-muted">{candidate.designation}</div>
              </div>
              <Badge tone="success">{Math.round(candidate.final_score || 0)}</Badge>
            </div>
            <p className="mt-2 text-xs text-ats-muted">{candidate.ranking_reason}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
