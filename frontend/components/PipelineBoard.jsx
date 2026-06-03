import { CandidateCard } from "./CandidateCard.jsx";

const stages = [
  ["review", "Review"],
  ["shortlisted", "Shortlisted"],
  ["communication", "Communication"],
  ["interview_scheduling", "Interview"],
  ["offer", "Offer"]
];

export function PipelineBoard({ candidates }) {
  const grouped = Object.fromEntries(stages.map(([key]) => [key, []]));
  candidates.forEach((candidate) => {
    const stage = candidate.stage || "review";
    if (grouped[stage]) grouped[stage].push(candidate);
  });

  return (
    <section className="grid min-h-[520px] gap-3 overflow-x-auto pb-2 lg:grid-cols-5">
      {stages.map(([key, label]) => (
        <div key={key} className="min-w-64 rounded-md border border-ats-line bg-ats-surface">
          <div className="sticky top-[65px] z-10 flex items-center justify-between border-b border-ats-line bg-ats-surface px-3 py-2">
            <h2 className="text-sm font-semibold text-ats-ink">{label}</h2>
            <span className="rounded-full bg-white px-2 py-1 text-xs text-ats-muted">{grouped[key].length}</span>
          </div>
          <div className="space-y-2 p-2">
            {grouped[key].map((candidate) => (
              <CandidateCard key={candidate.resume_id || candidate.id} candidate={candidate} />
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}
