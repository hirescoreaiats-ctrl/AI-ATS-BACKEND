import { X } from "lucide-react";
import { Button } from "./Button.jsx";

export function Drawer({ open, title, onClose, children }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40">
      <button className="absolute inset-0 bg-slate-900/25" onClick={onClose} aria-label="Close drawer" />
      <aside className="absolute right-0 top-0 flex h-full w-full max-w-3xl flex-col border-l border-ats-line bg-white shadow-ats">
        <header className="flex items-center justify-between border-b border-ats-line px-5 py-4">
          <h2 className="text-base font-semibold text-ats-ink">{title}</h2>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close">
            <X size={18} />
          </Button>
        </header>
        <div className="flex-1 overflow-auto p-5 ats-scrollbar">{children}</div>
      </aside>
    </div>
  );
}
