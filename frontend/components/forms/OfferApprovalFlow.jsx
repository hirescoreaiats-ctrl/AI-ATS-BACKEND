import { CheckCircle2, CircleDollarSign, UserCheck } from "lucide-react";
import { Button } from "../design-system/Button.jsx";

export function OfferApprovalFlow({ candidate }) {
  const steps = ["Recruiter draft", "Finance approval", "Hiring manager approval", "Candidate sent"];
  return (
    <section className="rounded-md border border-ats-line bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2">
        <CircleDollarSign size={18} className="text-ats-brand" />
        <h2 className="text-sm font-semibold text-ats-ink">Offer Approval Flow</h2>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-4">
        {steps.map((step, index) => (
          <div key={step} className="rounded-md bg-ats-surface p-3">
            {index === 0 ? <CheckCircle2 size={18} className="text-ats-success" /> : <UserCheck size={18} className="text-ats-muted" />}
            <div className="mt-2 text-sm font-medium text-ats-ink">{step}</div>
            <div className="text-xs text-ats-muted">{candidate?.full_name || "Selected candidate"}</div>
          </div>
        ))}
      </div>
      <Button className="mt-4" variant="secondary">Start approval</Button>
    </section>
  );
}
