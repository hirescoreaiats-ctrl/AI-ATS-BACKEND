import { Search } from "lucide-react";
import { CandidateWorkspace } from "../components/candidates/CandidateWorkspace.jsx";
import { Badge } from "../components/design-system/Badge.jsx";

export function TalentRoute({ candidates, query }) {
  return (
    <div className="space-y-5 p-6">
      <section className="rounded-md border border-ats-line bg-white p-4 shadow-sm">
        <div className="flex items-center gap-2">
          <Search size={18} className="text-ats-brand" />
          <h2 className="text-sm font-semibold text-ats-ink">Hybrid Talent Discovery</h2>
        </div>
        <p className="mt-2 text-sm text-ats-muted">Semantic, keyword, boolean, AI confidence, and ATS stage signals are blended into ranking.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Badge tone="brand">{query}</Badge>
          <Badge>Semantic + keyword</Badge>
          <Badge>Redis cached</Badge>
        </div>
      </section>
      <CandidateWorkspace candidates={candidates} />
    </div>
  );
}
