import { Search } from "lucide-react";
import { Button } from "./Button.jsx";

export function CommandMenu({ open, query, onQuery, onClose, commands = [] }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-slate-900/30 p-6 pt-24">
      <section className="w-full max-w-2xl rounded-md border border-ats-line bg-white shadow-ats">
        <div className="relative border-b border-ats-line">
          <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-ats-muted" />
          <input
            autoFocus
            value={query}
            onChange={(event) => onQuery(event.target.value)}
            placeholder="Search candidates, run actions, ask AI"
            className="h-12 w-full rounded-t-md pl-11 pr-4 text-sm outline-none"
          />
        </div>
        <div className="max-h-80 overflow-auto p-2 ats-scrollbar">
          {commands.map((command) => (
            <button key={command.label} onClick={command.action} className="flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm hover:bg-ats-surface">
              <span className="font-medium text-ats-ink">{command.label}</span>
              <span className="text-xs text-ats-muted">{command.hint}</span>
            </button>
          ))}
        </div>
        <footer className="flex justify-end border-t border-ats-line p-3">
          <Button variant="secondary" size="sm" onClick={onClose}>Close</Button>
        </footer>
      </section>
    </div>
  );
}
