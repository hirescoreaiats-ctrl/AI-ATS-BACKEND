export function ATSDataTable({ rows, onRowClick }) {
  return (
    <div className="overflow-hidden rounded-md border border-ats-line bg-white shadow-sm">
      <div className="max-h-[520px] overflow-auto ats-scrollbar">
        <table className="min-w-full border-separate border-spacing-0 text-sm">
          <thead className="sticky top-0 z-10 bg-ats-surface text-left text-xs font-semibold uppercase tracking-normal text-ats-muted">
            <tr>
              {["Candidate", "Role", "Score", "Confidence", "Stage", "Recommendation"].map((head) => (
                <th key={head} className="border-b border-ats-line px-4 py-3">{head}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.resume_id || row.id}
                className="cursor-pointer hover:bg-blue-50/40"
                onClick={() => onRowClick?.(row)}
              >
                <td className="border-b border-ats-line px-4 py-3">
                  <div className="font-medium text-ats-ink">{row.full_name || row.name}</div>
                  <div className="text-xs text-ats-muted">{row.email}</div>
                </td>
                <td className="border-b border-ats-line px-4 py-3 text-ats-muted">{row.designation}</td>
                <td className="border-b border-ats-line px-4 py-3 font-semibold text-ats-ink">{Math.round(row.final_score || 0)}</td>
                <td className="border-b border-ats-line px-4 py-3 text-ats-muted">{Math.round(row.confidence_score || 0)}%</td>
                <td className="border-b border-ats-line px-4 py-3">
                  <span className="rounded-full bg-ats-surface px-2 py-1 text-xs text-ats-muted">{row.stage || "review"}</span>
                </td>
                <td className="border-b border-ats-line px-4 py-3 text-ats-muted">{row.ai_recommendation || "review"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
