import { BarChart3, BriefcaseBusiness, Building2, Inbox, KanbanSquare, Search, Settings, Sparkles, UsersRound } from "lucide-react";

const items = [
  ["Pipeline", KanbanSquare, "/pipeline"],
  ["Candidates", UsersRound, "/candidates"],
  ["Talent Search", Search, "/talent"],
  ["Inbox", Inbox, "/inbox"],
  ["Copilot", Sparkles, "/copilot"],
  ["Analytics", BarChart3, "/analytics"],
  ["Jobs", BriefcaseBusiness, "/jobs"],
  ["Organization", Building2, "/organization"],
  ["Settings", Settings, "/settings"]
];

export function EnterpriseSidebar({ active = "/pipeline", onNavigate }) {
  return (
    <aside className="sticky top-0 flex h-screen w-72 shrink-0 flex-col border-r border-ats-line bg-white">
      <div className="border-b border-ats-line px-5 py-4">
        <div className="text-xs font-semibold uppercase tracking-normal text-ats-muted">AI Recruiting OS</div>
        <div className="mt-1 text-lg font-semibold text-ats-ink">Talent Command</div>
      </div>
      <nav className="flex-1 space-y-1 px-3 py-4">
        {items.map(([label, Icon, href]) => (
          <button
            key={href}
            onClick={() => onNavigate?.(href)}
            className={`flex h-10 w-full items-center gap-3 rounded-md px-3 text-sm ${active === href ? "bg-blue-50 font-semibold text-ats-brand" : "text-ats-muted hover:bg-ats-surface hover:text-ats-ink"}`}
          >
            <Icon size={18} />
            <span>{label}</span>
          </button>
        ))}
      </nav>
    </aside>
  );
}
