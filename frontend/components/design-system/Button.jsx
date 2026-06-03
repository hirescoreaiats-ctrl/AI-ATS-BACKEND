import { cn } from "../../lib/classNames.js";

export function Button({ variant = "primary", size = "md", className = "", ...props }) {
  const variants = {
    primary: "bg-ats-brand text-white hover:bg-blue-700",
    secondary: "border border-ats-line bg-white text-ats-ink hover:bg-ats-surface",
    ghost: "text-ats-muted hover:bg-ats-surface hover:text-ats-ink",
    danger: "bg-red-600 text-white hover:bg-red-700"
  };
  const sizes = {
    sm: "h-8 px-3 text-xs",
    md: "h-10 px-4 text-sm",
    icon: "h-9 w-9 p-0"
  };
  return <button className={cn("inline-flex items-center justify-center gap-2 rounded-md font-semibold outline-none focus:ring-2 focus:ring-blue-100", variants[variant], sizes[size], className)} {...props} />;
}
