import { Building2, UserPlus, UsersRound } from "lucide-react";
import { Button } from "../components/design-system/Button.jsx";

export function OrganizationRoute() {
  return (
    <div className="space-y-5 p-6">
      <section className="rounded-md border border-ats-line bg-white p-4 shadow-sm">
        <div className="flex items-center gap-2">
          <Building2 size={18} className="text-ats-brand" />
          <h2 className="text-sm font-semibold text-ats-ink">Organization Settings</h2>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <Panel icon={UsersRound} title="Teams" body="Recruiting, hiring manager, and coordinator team structures." />
          <Panel icon={UserPlus} title="Invitations" body="Invite recruiters and hiring managers with role-scoped permissions." />
          <Panel icon={Building2} title="Departments" body="Department pipelines and analytics segmentation." />
        </div>
        <Button className="mt-4" variant="secondary">Invite teammate</Button>
      </section>
    </div>
  );
}

function Panel({ icon: Icon, title, body }) {
  return (
    <div className="rounded-md bg-ats-surface p-4">
      <Icon size={18} className="text-ats-muted" />
      <div className="mt-2 text-sm font-semibold text-ats-ink">{title}</div>
      <div className="mt-1 text-xs text-ats-muted">{body}</div>
    </div>
  );
}
