// Shared form-control classes. The focus ring is the solid navy `focus-visible` outline: never pair it
// with `focus:outline-none`, which in Tailwind v4 sets the outline style to none and hides the ring.
export const inputClass =
  "w-full rounded-md border border-line bg-white px-2.5 py-1.5 text-sm font-medium text-ink transition-colors duration-150 " +
  "hover:border-line-strong focus:border-navy focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-navy " +
  "disabled:cursor-not-allowed disabled:opacity-60 aria-[invalid=true]:border-red";

/** The small bold label above a field (the sketch's 11px field labels). */
export const fieldLabelClass = "mb-1 block text-[11px] font-bold uppercase tracking-[0.06em] text-muted";
