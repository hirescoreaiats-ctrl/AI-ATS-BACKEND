import { AIRecruiterCopilot } from "../components/ai/AIRecruiterCopilot.jsx";
import { AIRecommendationPanel } from "../components/ai/AIRecommendationPanel.jsx";

export function CopilotRoute({ candidates }) {
  return (
    <div className="grid gap-5 p-6 xl:grid-cols-[1fr_360px]">
      <AIRecruiterCopilot />
      <AIRecommendationPanel candidates={candidates} />
    </div>
  );
}
