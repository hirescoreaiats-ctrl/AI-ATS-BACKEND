import { BarChart3, BriefcaseBusiness, CalendarClock, KanbanSquare, Search, Sparkles, UsersRound } from "lucide-react";

const nav = [
  ["Pipeline", KanbanSquare],
  ["Candidates", UsersRound],
  ["Jobs", BriefcaseBusiness],
  ["Copilot", Sparkles],
  ["Interviews", CalendarClock],
  ["Analytics", BarChart3],
  ["Search", Search]
];

export function RecruiterSidebar() {
  return (
    <aside className="sticky top-0 flex h-screen w-64 shrink-0 flex-col border-r border-ats-line bg-ats-panel">
      <div className="border-b border-ats-line px-5 py-4">
        <div className="text-sm font-semibold text-ats-muted">HireScore AI</div>
        <div className="mt-1 text-lg font-semibold text-ats-ink">Recruiting OS</div>
      </div>
      <nav className="flex-1 space-y-1 px-3 py-4">
        {nav.map(([label, Icon], index) => (
          <button
            key={label}
            className={`flex h-10 w-full items-center gap-3 rounded-md px-3 text-sm ${index === 0 ? "bg-blue-50 font-semibold text-ats-brand" : "text-ats-muted hover:bg-ats-surface hover:text-ats-ink"}`}
          >
            <Icon size={18} />
            <span>{label}</span>
          </button>
        ))}
      </nav>
      <div className="border-t border-ats-line p-4 text-xs text-ats-muted">Workspace: Talent Acquisition</div>
    </aside>
  );
}
