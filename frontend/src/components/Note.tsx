import type { ReactNode } from "react";

export type NoteTone = "red" | "amber" | "info";

const TONES: Record<NoteTone, string> = {
  red: "border-red-line bg-red-bg text-red",
  amber: "border-amber-line bg-amber-bg text-amber",
  info: "border-line bg-cream text-ink",
};

/** A tinted inline note: red for what blocks verifying, amber for what to check, cream for plain info. */
export function Note({
  tone,
  icon,
  children,
  role,
  className = "",
}: {
  tone: NoteTone;
  icon?: ReactNode;
  children: ReactNode;
  role?: "alert" | "status" | "note";
  className?: string;
}) {
  return (
    <div role={role} className={`flex items-start gap-2.5 rounded-md border px-3 py-2.5 text-[13px] font-semibold ${TONES[tone]} ${className}`}>
      {icon && <span className="mt-px shrink-0 [&>svg]:size-4">{icon}</span>}
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
