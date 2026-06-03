export function CandidateCard({ candidate, compact = false }) {
  const score = Math.round(candidate.final_score || candidate.score || 0);
  return (
    <article className="rounded-md border border-ats-line bg-white p-3 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold text-ats-ink">{candidate.full_name || candidate.name}</h3>
          <p className="truncate text-xs text-ats-muted">{candidate.designation || candidate.email}</p>
        </div>
        <span className={`rounded-full px-2 py-1 text-xs font-semibold ${score >= 75 ? "bg-emerald-50 text-ats-success" : score >= 55 ? "bg-amber-50 text-ats-warning" : "bg-red-50 text-ats-danger"}`}>
          {score}
        </span>
      </div>
      {!compact && (
        <>
          <div className="mt-3 line-clamp-2 text-xs text-ats-muted">{candidate.ranking_reason || candidate.reason}</div>
          <div className="mt-3 flex flex-wrap gap-1">
            {(candidate.tags || candidate.key_skills?.split(",") || []).slice(0, 4).map((tag) => (
              <span key={tag} className="rounded bg-ats-surface px-2 py-1 text-xs text-ats-muted">{tag.trim()}</span>
            ))}
          </div>
        </>
      )}
    </article>
  );
}
