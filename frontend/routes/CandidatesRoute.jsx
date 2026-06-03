import { CandidateWorkspace } from "../components/candidates/CandidateWorkspace.jsx";

export function CandidatesRoute({ candidates }) {
  return (
    <div className="space-y-5 p-6">
      <section>
        <h2 className="text-lg font-semibold text-ats-ink">Candidate Workspace</h2>
        <p className="mt-1 text-sm text-ats-muted">AI summaries, score breakdowns, resume context, collaboration, and activity history.</p>
      </section>
      <CandidateWorkspace candidates={candidates} />
    </div>
  );
}
