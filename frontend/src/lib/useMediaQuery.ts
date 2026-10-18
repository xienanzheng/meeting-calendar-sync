import { useSyncExternalStore } from "react";

/** Whether a media query matches now; re-renders when it flips (e.g. the source panel becoming a drawer). */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const list = window.matchMedia(query);
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}
