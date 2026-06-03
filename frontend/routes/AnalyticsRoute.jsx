import { TalentAnalyticsDashboard } from "../components/analytics/TalentAnalyticsDashboard.jsx";
import { PipelineAnalytics } from "../components/pipeline/PipelineAnalytics.jsx";

export function AnalyticsRoute({ candidates }) {
  return (
    <div className="space-y-5 p-6">
      <TalentAnalyticsDashboard candidates={candidates} />
      <PipelineAnalytics candidates={candidates} />
      <section className="rounded-md border border-ats-line bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-ats-ink">Hiring Bottleneck Analysis</h2>
        <div className="mt-4 h-48 rounded-md bg-ats-surface p-4 text-sm text-ats-muted">
          Pipeline conversion, feedback completion, stage aging, and source quality metrics are ready for API-backed charts.
        </div>
      </section>
    </div>
  );
}
