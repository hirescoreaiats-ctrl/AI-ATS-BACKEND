import { useMemo } from "react";
import { Badge } from "../design-system/Badge.jsx";
import { Drawer } from "../design-system/Drawer.jsx";
import { CandidateTimeline } from "./CandidateTimeline.jsx";
import { HiringActivityFeed } from "./HiringActivityFeed.jsx";

export function CandidateProfileDrawer({ candidate, open, onClose, timeline }) {
  const skills = useMemo(() => (candidate?.key_skills || "").split(",").map((skill) => skill.trim()).filter(Boolean), [candidate]);
  const missing = useMemo(() => (candidate?.missing_skills || "").split(",").map((skill) => skill.trim()).filter(Boolean), [candidate]);

  return (
    <Drawer open={open} onClose={onClose} title={candidate?.full_name || "Candidate profile"}>
      {candidate && (
        <div className="space-y-5">
          <section className="rounded-md border border-ats-line bg-white p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-ats-ink">{candidate.full_name}</h2>
                <p className="text-sm text-ats-muted">{candidate.designation} | {candidate.email}</p>
              </div>
              <Badge tone={(candidate.final_score || 0) >= 75 ? "success" : "warning"}>{Math.round(candidate.final_score || 0)} fit</Badge>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-3">
              <Metric label="AI confidence" value={`${Math.round(candidate.confidence_score || 0)}%`} />
              <Metric label="Stage" value={candidate.stage || "review"} />
              <Metric label="Recommendation" value={candidate.ai_recommendation || "review"} />
            </div>
          </section>
          <section className="grid gap-4 lg:grid-cols-2">
            <Panel title="AI Hiring Summary">
              <p className="text-sm text-ats-muted">{candidate.ranking_reason || "AI summary will appear after parsing and scoring."}</p>
            </Panel>
            <Panel title="Risk Analysis">
              <p className="text-sm text-ats-muted">{missing.length ? `Validate gaps in ${missing.slice(0, 4).join(", ")}.` : "No major missing-skill risk detected."}</p>
            </Panel>
            <Panel title="Skill Graph">
              <div className="flex flex-wrap gap-2">{skills.slice(0, 12).map((skill) => <Badge key={skill} tone="brand">{skill}</Badge>)}</div>
            </Panel>
            <Panel title="Resume Viewer">
              <div className="max-h-52 overflow-auto rounded bg-ats-surface p-3 text-xs text-ats-muted ats-scrollbar">{candidate.resume_text || "Resume text preview is available after candidate ingestion."}</div>
            </Panel>
          </section>
          <CandidateTimeline activities={timeline?.activities} stageHistory={timeline?.history} />
          <HiringActivityFeed notes={timeline?.notes} />
        </div>
      )}
    </Drawer>
  );
}

function Metric({ label, value }) {
  return (
    <div className="rounded-md bg-ats-surface p-3">
      <div className="text-xs uppercase tracking-normal text-ats-muted">{label}</div>
      <div className="mt-1 text-sm font-semibold text-ats-ink">{value}</div>
    </div>
  );
}

function Panel({ title, children }) {
  return (
    <section className="rounded-md border border-ats-line bg-white p-4">
      <h3 className="text-sm font-semibold text-ats-ink">{title}</h3>
      <div className="mt-3">{children}</div>
    </section>
  );
}
