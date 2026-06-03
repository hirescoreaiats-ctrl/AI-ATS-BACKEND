import { useMemo, useState } from "react";
import { AIInsightPanel } from "../components/AIInsightPanel.jsx";
import { ATSDataTable } from "../components/ATSDataTable.jsx";
import { AnalyticsCards } from "../components/AnalyticsCards.jsx";
import { FilterBar } from "../components/FilterBar.jsx";
import { InterviewScheduler } from "../components/InterviewScheduler.jsx";
import { PipelineBoard } from "../components/PipelineBoard.jsx";
import { RecruiterWorkspaceLayout } from "../layouts/RecruiterWorkspaceLayout.jsx";
import { useDebouncedValue } from "../hooks/useDebouncedValue.js";

const sampleCandidates = [
  { id: "1", full_name: "Aarav Mehta", email: "aarav@example.com", designation: "Senior Backend Engineer", final_score: 88, confidence_score: 84, stage: "shortlisted", ai_recommendation: "shortlisted", key_skills: "Python, FastAPI, PostgreSQL", ranking_reason: "Strong backend match with relevant systems experience." },
  { id: "2", full_name: "Nisha Rao", email: "nisha@example.com", designation: "Data Analyst", final_score: 73, confidence_score: 77, stage: "communication", ai_recommendation: "shortlisted", key_skills: "SQL, Power BI, Python", ranking_reason: "Good analytics fit with transferable BI skills." },
  { id: "3", full_name: "Kabir Shah", email: "kabir@example.com", designation: "Full Stack Developer", final_score: 61, confidence_score: 68, stage: "review", ai_recommendation: "in_review", key_skills: "React, Node.js, AWS", ranking_reason: "Solid adjacent skills; needs recruiter validation." }
];

export function EnterpriseATSPage() {
  const [search, setSearch] = useState("");
  const [stage, setStage] = useState("all");
  const debouncedSearch = useDebouncedValue(search);

  const candidates = useMemo(() => {
    const query = debouncedSearch.toLowerCase();
    return sampleCandidates.filter((candidate) => {
      const matchesStage = stage === "all" || candidate.stage === stage;
      const matchesSearch = !query || JSON.stringify(candidate).toLowerCase().includes(query);
      return matchesStage && matchesSearch;
    });
  }, [debouncedSearch, stage]);

  const metrics = [
    { kind: "applicants", label: "Applicants", value: "248", caption: "Across active roles" },
    { kind: "shortlisted", label: "Shortlisted", value: "37", caption: "AI and recruiter approved" },
    { kind: "time", label: "Time to screen", value: "1.8d", caption: "Median this week" },
    { kind: "conversion", label: "Interview rate", value: "24%", caption: "From communication stage" }
  ];

  return (
    <RecruiterWorkspaceLayout>
      <header className="border-b border-ats-line bg-white px-6 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-ats-ink">Senior Backend Engineer Pipeline</h1>
            <p className="mt-1 text-sm text-ats-muted">AI-ranked candidates, collaborative hiring, interviews, and offers in one recruiter workflow.</p>
          </div>
          <button className="rounded-md bg-ats-brand px-4 py-2 text-sm font-semibold text-white shadow-sm">Create job</button>
        </div>
      </header>
      <FilterBar search={search} onSearch={setSearch} stage={stage} onStage={setStage} />
      <div className="space-y-5 p-6">
        <AnalyticsCards metrics={metrics} />
        <div className="grid gap-5 xl:grid-cols-[1fr_320px]">
          <PipelineBoard candidates={candidates} />
          <AIInsightPanel summary={{ pipeline_health: "healthy", next_best_actions: ["Send assessments to 6 interested candidates.", "Collect scorecards for 3 completed interviews.", "Review 4 high-score duplicate candidate profiles."] }} />
        </div>
        <InterviewScheduler />
        <ATSDataTable rows={candidates} />
      </div>
    </RecruiterWorkspaceLayout>
  );
}
