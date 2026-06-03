import { HiringScorecards } from "../components/candidates/HiringScorecards.jsx";
import { InterviewScheduler } from "../components/forms/InterviewScheduler.jsx";

export function InterviewsRoute() {
  return (
    <div className="space-y-5 p-6">
      <InterviewScheduler />
      <HiringScorecards />
    </div>
  );
}
