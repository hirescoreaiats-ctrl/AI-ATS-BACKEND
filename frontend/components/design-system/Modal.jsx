import { Button } from "./Button.jsx";

export function Modal({ open, title, onClose, children, footer }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/30 p-4">
      <section className="w-full max-w-xl rounded-md border border-ats-line bg-white shadow-ats">
        <header className="border-b border-ats-line px-5 py-4">
          <h2 className="text-base font-semibold text-ats-ink">{title}</h2>
        </header>
        <div className="p-5">{children}</div>
        <footer className="flex justify-end gap-2 border-t border-ats-line px-5 py-3">
          {footer || <Button variant="secondary" onClick={onClose}>Close</Button>}
        </footer>
      </section>
    </div>
  );
}
