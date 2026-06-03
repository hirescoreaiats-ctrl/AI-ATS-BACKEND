import { Command, Download, Mail, MoveRight, Plus, Search, Sparkles } from "lucide-react";
import { Button } from "../design-system/Button.jsx";

export function RecruiterCommandBar({ query, onQuery, onBulkMove, onOutreach, onExport, onCandidate, onCopilot }) {
  return (
    <div className="sticky top-0 z-20 flex flex-wrap items-center gap-3 border-b border-ats-line bg-ats-surface/95 px-6 py-3 backdrop-blur">
      <div className="relative min-w-80 flex-1">
        <Search size={17} className="absolute left-3 top-1/2 -translate-y-1/2 text-ats-muted" />
        <input
          value={query}
          onChange={(event) => onQuery(event.target.value)}
          placeholder="Boolean or semantic search"
          className="h-10 w-full rounded-md border border-ats-line bg-white pl-9 pr-3 text-sm outline-none focus:border-ats-brand focus:ring-2 focus:ring-blue-100"
        />
      </div>
      <Button variant="secondary" onClick={onBulkMove}><MoveRight size={17} />Move</Button>
      <Button variant="secondary" onClick={onOutreach}><Mail size={17} />Outreach</Button>
      <Button variant="secondary" onClick={onExport}><Download size={17} />Export</Button>
      <Button variant="secondary" onClick={onCandidate}><Plus size={17} />Candidate</Button>
      <Button onClick={onCopilot}><Sparkles size={17} />Copilot</Button>
      <div className="hidden items-center gap-1 text-xs text-ats-muted xl:flex"><Command size={14} />K</div>
    </div>
  );
}
