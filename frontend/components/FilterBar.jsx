import { Search, SlidersHorizontal } from "lucide-react";

export function FilterBar({ search, onSearch, stage, onStage }) {
  return (
    <div className="sticky top-0 z-10 flex flex-wrap items-center gap-3 border-b border-ats-line bg-ats-surface/95 px-6 py-3 backdrop-blur">
      <div className="relative min-w-72 flex-1">
        <Search size={17} className="absolute left-3 top-1/2 -translate-y-1/2 text-ats-muted" />
        <input
          value={search}
          onChange={(event) => onSearch(event.target.value)}
          placeholder="Search candidates, skills, roles"
          className="h-10 w-full rounded-md border border-ats-line bg-white pl-9 pr-3 text-sm outline-none focus:border-ats-brand focus:ring-2 focus:ring-blue-100"
        />
      </div>
      <select
        value={stage}
        onChange={(event) => onStage(event.target.value)}
        className="h-10 rounded-md border border-ats-line bg-white px-3 text-sm text-ats-ink outline-none focus:border-ats-brand"
      >
        <option value="all">All stages</option>
        <option value="review">Review</option>
        <option value="shortlisted">Shortlisted</option>
        <option value="communication">Communication</option>
        <option value="interview_scheduling">Interview</option>
        <option value="offer">Offer</option>
      </select>
      <button className="inline-flex h-10 items-center gap-2 rounded-md border border-ats-line bg-white px-3 text-sm font-medium text-ats-ink hover:bg-ats-surface">
        <SlidersHorizontal size={17} />
        Filters
      </button>
    </div>
  );
}
