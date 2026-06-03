import { useState } from "react";
import { AIRecommendationPanel } from "../components/ai/AIRecommendationPanel.jsx";
import { CandidateProfileDrawer } from "../components/candidates/CandidateProfileDrawer.jsx";
import { OfferApprovalFlow } from "../components/forms/OfferApprovalFlow.jsx";
import { PipelineAnalytics } from "../components/pipeline/PipelineAnalytics.jsx";
import { HiringPipelineBoard } from "../components/pipeline/HiringPipelineBoard.jsx";

export function PipelineRoute({ candidates }) {
  const [selected, setSelected] = useState(null);
  return (
    <div className="space-y-5 p-6">
      <PipelineAnalytics candidates={candidates} />
      <div className="grid gap-5 xl:grid-cols-[1fr_340px]">
        <HiringPipelineBoard candidates={candidates} onCandidateOpen={setSelected} />
        <div className="space-y-5">
          <AIRecommendationPanel candidates={candidates} />
          <OfferApprovalFlow candidate={selected || candidates[0]} />
        </div>
      </div>
      <CandidateProfileDrawer candidate={selected} open={Boolean(selected)} onClose={() => setSelected(null)} />
    </div>
  );
}
