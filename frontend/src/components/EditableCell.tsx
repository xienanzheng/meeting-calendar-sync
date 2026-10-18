import { Loader2, Pencil } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { errorMessage } from "../api";
import { inputClass } from "./fields";

export type EditableTone = "light" | "navy";

const VIEW: Record<EditableTone, string> = {
  light: "px-2.5 py-1.5 hover:bg-cream",
  navy: "-mx-1.5 px-1.5 py-0.5 text-white hover:bg-navy-2",
};

const INPUT: Record<EditableTone, string> = {
  light: `${inputClass} pr-8`,
  navy:
    "w-full rounded-md border border-white/35 bg-navy-2 px-1.5 py-0.5 pr-7 text-white caret-beige " +
    "focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-beige aria-[invalid=true]:border-red-on-navy",
};

/**
 * Text that reads as text and becomes an input on click. Enter or blur saves, Esc cancels.
 * `onSave` rejects with an ApiError to keep it open and show the server's message.
 * `tone="navy"` is the variant for the top bar; its error floats under the bar instead of pushing it taller.
 */
export function EditableCell({
  value,
  label,
  placeholder,
  type = "text",
  muted = false,
  tone = "light",
  textClassName = "",
  validate,
  onSave,
}: {
  value: string;
  label: string;
  placeholder: string;
  type?: "text" | "email";
  muted?: boolean;
  tone?: EditableTone;
  /** Font classes shared by the text and the input, so opening the editor doesn't shift anything. */
  textClassName?: string;
  validate?: (value: string) => string | null;
  onSave: (value: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const busy = useRef(false);
  const skipBlur = useRef(false); // set once the edit is finished, so the unmount blur doesn't save again
  const failedDraft = useRef<string | null>(null); // a value the server just refused; blur doesn't resend it
  const viewRef = useRef<HTMLButtonElement>(null);
  const returnFocus = useRef(false);

  useEffect(() => {
    if (!editing && returnFocus.current) {
      returnFocus.current = false;
      viewRef.current?.focus();
    }
  }, [editing]);

  function open() {
    skipBlur.current = false;
    failedDraft.current = null;
    setDraft(value);
    setError(null);
    setEditing(true);
  }

  function close(keyboard: boolean) {
    skipBlur.current = true;
    returnFocus.current = keyboard;
    setError(null);
    setEditing(false);
  }

  async function commit(keyboard: boolean) {
    if (busy.current) return;
    if (draft.trim() === value.trim()) return close(keyboard);
    const problem = validate?.(draft) ?? null;
    if (problem) {
      setError(problem);
      return;
    }
    busy.current = true;
    setSaving(true);
    try {
      await onSave(draft);
      close(keyboard);
    } catch (err) {
      failedDraft.current = draft;
      setError(errorMessage(err));
    } finally {
      busy.current = false;
      setSaving(false);
    }
  }

  const navy = tone === "navy";

  if (!editing) {
    const textTone = navy ? "text-white" : value ? (muted ? "text-muted" : "text-ink") : "text-muted";
    return (
      <button
        ref={viewRef}
        type="button"
        onClick={open}
        className={`group flex w-full min-w-0 items-center gap-2 rounded-md text-left transition-colors duration-150 ${VIEW[tone]}`}
      >
        <span className="sr-only">Edit {label}: </span>
        <span className={`truncate ${textTone} ${textClassName}`}>{value || placeholder}</span>
        <Pencil
          className={`ml-auto size-3.5 shrink-0 opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100 ${navy ? "text-white/70" : "text-muted"}`}
          aria-hidden="true"
        />
      </button>
    );
  }

  return (
    <div className="relative">
      <div className="relative">
        <input
          autoFocus
          type={type}
          value={draft}
          readOnly={saving}
          aria-busy={saving || undefined}
          aria-label={label}
          aria-invalid={error ? true : undefined}
          placeholder={placeholder}
          onChange={(event) => {
            setDraft(event.target.value);
            setError(null);
          }}
          onBlur={() => {
            if (!skipBlur.current && draft !== failedDraft.current) commit(false);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              commit(true);
            } else if (event.key === "Escape") {
              event.preventDefault();
              close(true);
            }
          }}
          className={`${INPUT[tone]} ${textClassName}`}
        />
        {saving && (
          <Loader2
            className={`absolute right-2 top-1/2 size-3.5 -translate-y-1/2 animate-spin ${navy ? "text-white/70" : "text-muted"}`}
            aria-hidden="true"
          />
        )}
      </div>
      {error && (
        <p
          role="alert"
          className={
            navy
              ? "absolute left-0 top-full z-30 mt-2 w-max max-w-[360px] rounded-md border border-red-line bg-red-bg px-2.5 py-1.5 text-xs font-semibold text-red shadow-[0_4px_12px_rgba(24,41,88,0.18)]"
              : "mt-1 text-xs font-semibold text-red"
          }
        >
          {error}
        </p>
      )}
    </div>
  );
}
