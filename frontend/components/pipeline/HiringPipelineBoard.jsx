import { ENTERPRISE_PIPELINE_STAGES } from "../../lib/pipelineStages.js";
import { CandidateCard } from "../cards/CandidateCard.jsx";

export function HiringPipelineBoard({ candidates = [], onCandidateOpen }) {
  const grouped = Object.fromEntries(ENTERPRISE_PIPELINE_STAGES.map((stage) => [stage.key, []]));
  candidates.forEach((candidate) => {
    const stage = candidate.stage || "recruiter_review";
    (grouped[stage] || grouped.recruiter_review).push(candidate);
  });

  return (
    <section className="grid gap-3 overflow-x-auto pb-3 xl:grid-cols-4 2xl:grid-cols-6">
      {ENTERPRISE_PIPELINE_STAGES.map((stage) => (
        <div key={stage.key} className="min-w-72 rounded-md border border-ats-line bg-ats-surface">
          <header className="sticky top-[65px] z-10 flex items-center justify-between border-b border-ats-line bg-ats-surface px-3 py-2">
            <h2 className="text-sm font-semibold text-ats-ink">{stage.name}</h2>
            <span className="rounded-full bg-white px-2 py-1 text-xs text-ats-muted">{grouped[stage.key]?.length || 0}</span>
          </header>
          <div className="space-y-2 p-2">
            {(grouped[stage.key] || []).map((candidate) => (
              <button key={candidate.resume_id || candidate.id} className="block w-full text-left" onClick={() => onCandidateOpen?.(candidate)}>
                <CandidateCard candidate={candidate} />
              </button>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}
