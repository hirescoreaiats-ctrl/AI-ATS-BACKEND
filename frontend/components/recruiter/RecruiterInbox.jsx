import { Mail, Reply, ShieldCheck } from "lucide-react";
import { Badge } from "../design-system/Badge.jsx";

const inbox = [
  { subject: "Candidate replied interested", meta: "Nisha Rao | 12m", tone: "success" },
  { subject: "Scorecard overdue", meta: "Technical panel | 2h", tone: "warning" },
  { subject: "Offer approval requested", meta: "Aarav Mehta | Today", tone: "brand" }
];

export function RecruiterInbox() {
  return (
    <section className="rounded-md border border-ats-line bg-white shadow-sm">
      <header className="flex items-center gap-2 border-b border-ats-line px-4 py-3">
        <Mail size={18} className="text-ats-brand" />
        <h2 className="text-sm font-semibold text-ats-ink">Recruiter Inbox</h2>
      </header>
      <div className="divide-y divide-ats-line">
        {inbox.map((item) => (
          <div key={item.subject} className="flex items-center justify-between px-4 py-3">
            <div>
              <div className="text-sm font-medium text-ats-ink">{item.subject}</div>
              <div className="text-xs text-ats-muted">{item.meta}</div>
            </div>
            <Badge tone={item.tone}><ShieldCheck size={12} className="inline" /> Action</Badge>
          </div>
        ))}
      </div>
      <footer className="border-t border-ats-line px-4 py-3 text-sm text-ats-muted">
        <Reply size={15} className="mr-1 inline" /> Candidate communication and hiring-team reminders stay in one queue.
      </footer>
    </section>
  );
}
