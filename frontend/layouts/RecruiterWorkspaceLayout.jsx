import { RecruiterSidebar } from "../components/RecruiterSidebar.jsx";

export function RecruiterWorkspaceLayout({ children }) {
  return (
    <div className="flex min-h-screen bg-ats-surface">
      <RecruiterSidebar />
      <main className="min-w-0 flex-1">{children}</main>
    </div>
  );
}
