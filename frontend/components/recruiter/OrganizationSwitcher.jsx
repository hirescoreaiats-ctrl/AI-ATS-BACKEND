import { Building2, ChevronDown } from "lucide-react";

export function OrganizationSwitcher({ organizations = [{ name: "Talent Acquisition" }] }) {
  return (
    <button className="inline-flex h-10 items-center gap-2 rounded-md border border-ats-line bg-white px-3 text-sm font-medium text-ats-ink">
      <Building2 size={17} className="text-ats-muted" />
      <span>{organizations[0]?.name || "Workspace"}</span>
      <ChevronDown size={16} className="text-ats-muted" />
    </button>
  );
}
