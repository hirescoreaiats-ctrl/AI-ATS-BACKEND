import { cn } from "../../lib/classNames.js";

export function Badge({ tone = "neutral", children }) {
  const tones = {
    neutral: "bg-ats-surface text-ats-muted",
    success: "bg-emerald-50 text-ats-success",
    warning: "bg-amber-50 text-ats-warning",
    danger: "bg-red-50 text-ats-danger",
    brand: "bg-blue-50 text-ats-brand"
  };
  return <span className={cn("rounded-full px-2 py-1 text-xs font-semibold", tones[tone])}>{children}</span>;
}
