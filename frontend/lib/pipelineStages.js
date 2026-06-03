export const ENTERPRISE_PIPELINE_STAGES = [
  { key: "applied", name: "Applied" },
  { key: "ai_screening", name: "AI Screening" },
  { key: "recruiter_review", name: "Recruiter Review" },
  { key: "hiring_manager_review", name: "Hiring Manager Review" },
  { key: "technical_interview", name: "Technical Interview" },
  { key: "assessment", name: "Assessment" },
  { key: "final_interview", name: "Final Interview" },
  { key: "offer", name: "Offer" },
  { key: "hired", name: "Hired" },
  { key: "rejected", name: "Rejected" },
  { key: "archived", name: "Archived" }
];

export function stageLabel(stage) {
  return ENTERPRISE_PIPELINE_STAGES.find((item) => item.key === stage)?.name || "Recruiter Review";
}
