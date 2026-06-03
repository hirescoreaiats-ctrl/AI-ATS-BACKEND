import { MessageSquareText } from "lucide-react";

export function HiringActivityFeed({ notes = [] }) {
  return (
    <section className="rounded-md border border-ats-line bg-white">
      <header className="flex items-center gap-2 border-b border-ats-line px-4 py-3">
        <MessageSquareText size={17} className="text-ats-brand" />
        <h3 className="text-sm font-semibold text-ats-ink">Hiring Activity</h3>
      </header>
      <div className="space-y-3 p-4">
        {(notes.length ? notes : [{ body: "No recruiter notes yet. Add structured feedback after screening.", visibility: "team" }]).map((note, index) => (
          <article key={note.id || index} className="rounded-md bg-ats-surface p-3">
            <div className="text-sm text-ats-ink">{note.body}</div>
            <div className="mt-2 text-xs text-ats-muted">{note.visibility || "team"}</div>
          </article>
        ))}
      </div>
    </section>
  );
}
