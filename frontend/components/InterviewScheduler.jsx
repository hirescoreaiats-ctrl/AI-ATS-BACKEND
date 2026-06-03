import { CalendarClock, Video } from "lucide-react";

export function InterviewScheduler() {
  return (
    <section className="rounded-md border border-ats-line bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2">
        <CalendarClock size={18} className="text-ats-brand" />
        <h2 className="text-sm font-semibold text-ats-ink">Interview Scheduler</h2>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-4">
        <input type="datetime-local" className="h-10 rounded-md border border-ats-line px-3 text-sm outline-none focus:border-ats-brand" />
        <select className="h-10 rounded-md border border-ats-line px-3 text-sm outline-none focus:border-ats-brand">
          <option>Technical</option>
          <option>Hiring Manager</option>
          <option>Culture</option>
        </select>
        <input placeholder="Interviewer" className="h-10 rounded-md border border-ats-line px-3 text-sm outline-none focus:border-ats-brand" />
        <button className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-ats-brand px-4 text-sm font-semibold text-white">
          <Video size={17} />
          Schedule
        </button>
      </div>
    </section>
  );
}
