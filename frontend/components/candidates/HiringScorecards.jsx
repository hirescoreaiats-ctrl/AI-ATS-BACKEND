import { Star } from "lucide-react";

export function HiringScorecards() {
  const competencies = ["Technical depth", "Communication", "Ownership", "Role alignment"];
  return (
    <section className="rounded-md border border-ats-line bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2">
        <Star size={18} className="text-ats-brand" />
        <h2 className="text-sm font-semibold text-ats-ink">Hiring Scorecards</h2>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-4">
        {competencies.map((item) => (
          <label key={item} className="rounded-md bg-ats-surface p-3">
            <div className="text-sm font-medium text-ats-ink">{item}</div>
            <select className="mt-2 h-9 w-full rounded-md border border-ats-line bg-white px-2 text-sm">
              <option>Strong yes</option>
              <option>Yes</option>
              <option>Mixed</option>
              <option>No</option>
            </select>
          </label>
        ))}
      </div>
    </section>
  );
}
