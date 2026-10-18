import { Loader2, Pencil, UserPlus } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  ApiError,
  createAnalyst,
  deleteAnalyst,
  errorMessage,
  listRoster,
  updateAnalyst,
  type Analyst,
  type AnalystUpdate,
} from "../api";
import { Button, ConfirmButton } from "../components/Button";
import { ErrorNote } from "../components/ErrorNote";
import { Shell } from "../components/Shell";

type RowError = { message: string; conflict: boolean };

type Loadable<T> = { state: "loading" } | { state: "error"; message: string } | { state: "ready"; data: T };

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const splitAliases = (text: string) =>
  text
    .split(",")
    .map((a) => a.trim())
    .filter(Boolean);

const byName = (a: Analyst, b: Analyst) => a.name.localeCompare(b.name) || a.id - b.id;

function checkName(value: string): string | null {
  return value.trim() ? null : "Enter a name.";
}

function checkEmail(value: string): string | null {
  return EMAIL.test(value.trim()) ? null : "Enter an email address like name@example.com.";
}

const inputClass =
  "w-full rounded-md border border-line bg-white px-2.5 py-1.5 text-sm font-medium text-ink transition-colors duration-150 " +
  "hover:border-line-strong focus:border-navy focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-navy/25 " +
  "disabled:cursor-not-allowed disabled:opacity-60 aria-[invalid=true]:border-red";

/**
 * A table cell that reads as text and becomes an input on click. Enter or blur saves, Esc cancels.
 * `onSave` rejects with an ApiError to keep the cell open and show the server's message.
 */
function EditableCell({
  value,
  label,
  placeholder,
  type = "text",
  muted = false,
  validate,
  onSave,
}: {
  value: string;
  label: string;
  placeholder: string;
  type?: "text" | "email";
  muted?: boolean;
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

  if (!editing) {
    return (
      <button
        ref={viewRef}
        type="button"
        onClick={open}
        className="group flex w-full min-w-0 items-center gap-2 rounded-md px-2.5 py-1.5 text-left transition-colors duration-150 hover:bg-cream"
      >
        <span className="sr-only">Edit {label}: </span>
        <span className={`truncate ${value ? (muted ? "text-muted" : "text-ink") : "text-muted"}`}>{value || placeholder}</span>
        <Pencil
          className="ml-auto size-3.5 shrink-0 text-muted opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100"
          aria-hidden="true"
        />
      </button>
    );
  }

  return (
    <div>
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
          className={`${inputClass} pr-8`}
        />
        {saving && (
          <Loader2 className="absolute right-2.5 top-1/2 size-3.5 -translate-y-1/2 animate-spin text-muted" aria-hidden="true" />
        )}
      </div>
      {error && (
        <p role="alert" className="mt-1 text-xs font-semibold text-red">
          {error}
        </p>
      )}
    </div>
  );
}

function ActiveSwitch({ analyst, busy, onToggle }: { analyst: Analyst; busy: boolean; onToggle: () => void }) {
  return (
    <div className="flex items-center gap-2.5 px-2.5">
      <button
        type="button"
        role="switch"
        aria-checked={analyst.active}
        aria-label={`${analyst.name} is active`}
        disabled={busy}
        onClick={onToggle}
        className={[
          "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors duration-150",
          "disabled:cursor-progress",
          analyst.active ? "bg-navy hover:bg-navy-2" : "bg-line-strong hover:bg-stamp",
        ].join(" ")}
      >
        <span
          className={[
            "inline-block size-4 rounded-full bg-white shadow-[0_1px_2px_rgba(24,41,88,0.3)] transition-transform duration-150 ease-out",
            analyst.active ? "translate-x-[18px]" : "translate-x-0.5",
          ].join(" ")}
        />
      </button>
      <span aria-hidden="true" className={`text-[13px] font-semibold ${analyst.active ? "text-ink" : "text-muted"}`}>
        {analyst.active ? "Active" : "Inactive"}
      </span>
    </div>
  );
}

function AddColleague({ onAdded }: { onAdded: (analyst: Analyst) => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [aliases, setAliases] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<{ field: "name" | "email" | null; message: string } | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const nameProblem = checkName(name);
    if (nameProblem) return setError({ field: "name", message: nameProblem });
    const emailProblem = checkEmail(email);
    if (emailProblem) return setError({ field: "email", message: emailProblem });
    setSaving(true);
    setError(null);
    try {
      const created = await createAnalyst({ name: name.trim(), email: email.trim(), aliases: splitAliases(aliases) });
      onAdded(created);
      setName("");
      setEmail("");
      setAliases("");
      nameRef.current?.focus();
    } catch (err) {
      setError({ field: null, message: errorMessage(err) });
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <tr className="bg-head">
        <td className="px-2.5 py-3">
          <input
            ref={nameRef}
            form="add-colleague"
            value={name}
            onChange={(event) => setName(event.target.value)}
            readOnly={saving}
            aria-label="New colleague's name"
            aria-invalid={error?.field === "name" || undefined}
            placeholder="Name"
            className={inputClass}
          />
        </td>
        <td className="px-2.5 py-3">
          <input
            form="add-colleague"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            readOnly={saving}
            aria-label="New colleague's email"
            aria-invalid={error?.field === "email" || undefined}
            placeholder="name@example.com"
            className={inputClass}
          />
        </td>
        <td className="px-2.5 py-3">
          <input
            form="add-colleague"
            value={aliases}
            onChange={(event) => setAliases(event.target.value)}
            readOnly={saving}
            aria-label="New colleague's aliases, comma-separated"
            placeholder="Aliases, comma-separated"
            className={inputClass}
          />
        </td>
        <td className="px-5 py-3 text-right" colSpan={2}>
          <Button
            type="submit"
            form="add-colleague"
            variant="primary"
            size="sm"
            loading={saving}
            icon={<UserPlus className="size-3.5" aria-hidden="true" />}
          >
            Add colleague
          </Button>
        </td>
      </tr>
      {error && (
        <tr className="bg-head">
          <td colSpan={5} className="px-5 pb-3">
            <p role="alert" className="text-[13px] font-semibold text-red">
              {error.message}
            </p>
          </td>
        </tr>
      )}
      <tr hidden>
        <td>
          <form id="add-colleague" onSubmit={submit} noValidate />
        </td>
      </tr>
    </>
  );
}

export function RosterPage() {
  const [roster, setRoster] = useState<Loadable<Analyst[]>>({ state: "loading" });
  const [rowErrors, setRowErrors] = useState<Record<number, RowError>>({});
  const [busy, setBusy] = useState<Record<number, boolean>>({});

  const fetchRoster = useCallback(() => {
    listRoster().then(
      (data) => setRoster({ state: "ready", data: [...data].sort(byName) }),
      (error) => setRoster({ state: "error", message: errorMessage(error) }),
    );
  }, []);

  useEffect(fetchRoster, [fetchRoster]);

  const retry = () => {
    setRoster({ state: "loading" });
    fetchRoster();
  };

  const replace = (updated: Analyst) =>
    setRoster((current) =>
      current.state === "ready"
        ? { state: "ready", data: current.data.map((a) => (a.id === updated.id ? updated : a)).sort(byName) }
        : current,
    );

  const setRowError = (id: number, error: unknown) =>
    setRowErrors((errors) => {
      const next = { ...errors };
      if (error) next[id] = { message: errorMessage(error), conflict: error instanceof ApiError && error.status === 409 };
      else delete next[id];
      return next;
    });

  // Cell edits: errors stay in the cell (thrown back to EditableCell).
  async function save(analyst: Analyst, body: AnalystUpdate) {
    const updated = await updateAnalyst(analyst.id, body);
    replace(updated);
    setRowError(analyst.id, null);
  }

  async function toggleActive(analyst: Analyst) {
    setBusy((b) => ({ ...b, [analyst.id]: true }));
    try {
      replace(await updateAnalyst(analyst.id, { active: !analyst.active }));
      setRowError(analyst.id, null);
    } catch (error) {
      setRowError(analyst.id, error);
    } finally {
      setBusy((b) => ({ ...b, [analyst.id]: false }));
    }
  }

  async function remove(analyst: Analyst) {
    setBusy((b) => ({ ...b, [analyst.id]: true }));
    try {
      await deleteAnalyst(analyst.id);
      setRoster((current) =>
        current.state === "ready" ? { state: "ready", data: current.data.filter((a) => a.id !== analyst.id) } : current,
      );
      setRowError(analyst.id, null);
    } catch (error) {
      // 409: "This colleague is on meetings. Mark them inactive instead."
      setRowError(analyst.id, error);
    } finally {
      setBusy((b) => ({ ...b, [analyst.id]: false }));
    }
  }

  return (
    <Shell>
      <div className="mx-auto max-w-[1100px] px-7 pb-16 pt-9">
        <h1 className="text-[28px] font-bold leading-tight text-navy">Roster</h1>
        <p className="mt-1.5 max-w-[70ch] text-[15px] text-muted">
          Names printed in broker schedules are matched to these colleagues by name, alias or initials. Inactive colleagues
          stay on existing meetings but aren't matched in new uploads.
        </p>

        {roster.state === "loading" && (
          <p role="status" className="mt-7 flex items-center gap-2 text-sm text-muted">
            <Loader2 className="size-4 animate-spin" aria-hidden="true" /> Loading the roster…
          </p>
        )}
        {roster.state === "error" && (
          <div className="mt-7">
            <ErrorNote title="Couldn't load the roster." message={roster.message} onRetry={retry} retryLabel="Retry" />
          </div>
        )}
        {roster.state === "ready" && (
          <div className="relative mt-7 overflow-x-auto rounded-lg border border-line bg-white">
            <table className="w-full min-w-[820px] table-fixed border-collapse text-sm">
              <colgroup>
                <col className="w-[22%]" />
                <col className="w-[28%]" />
                <col />
                <col className="w-[140px]" />
                <col className="w-[150px]" />
              </colgroup>
              <thead>
                <tr className="border-b border-line bg-head text-left font-heading text-[11px] font-bold uppercase tracking-[0.08em] text-muted">
                  <th scope="col" className="px-5 py-2.5">Name</th>
                  <th scope="col" className="px-5 py-2.5">Email</th>
                  <th scope="col" className="px-5 py-2.5">Aliases</th>
                  <th scope="col" className="px-5 py-2.5">Active</th>
                  <th scope="col" className="px-5 py-2.5">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {roster.data.length === 0 && (
                  <tr className="border-b border-rule">
                    <td colSpan={5} className="px-5 py-10 text-center text-[15px] font-medium text-muted">
                      Add the colleagues whose calendars you manage.
                    </td>
                  </tr>
                )}
                {roster.data.map((analyst) => (
                  <RosterRow
                    key={analyst.id}
                    analyst={analyst}
                    busy={!!busy[analyst.id]}
                    error={rowErrors[analyst.id] ?? null}
                    onSave={(body) => save(analyst, body)}
                    onToggle={() => toggleActive(analyst)}
                    onDelete={() => remove(analyst)}
                  />
                ))}
                <AddColleague
                  onAdded={(created) =>
                    setRoster((current) =>
                      current.state === "ready" ? { state: "ready", data: [...current.data, created].sort(byName) } : current,
                    )
                  }
                />
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Shell>
  );
}

function RosterRow({
  analyst,
  busy,
  error,
  onSave,
  onToggle,
  onDelete,
}: {
  analyst: Analyst;
  busy: boolean;
  error: RowError | null;
  onSave: (body: AnalystUpdate) => Promise<void>;
  onToggle: () => void;
  onDelete: () => void;
}) {
  const muted = !analyst.active;
  return (
    <>
      <tr className={`align-top ${error ? "" : "border-b border-rule"}`}>
        <td className="px-2.5 py-2 font-semibold">
          <EditableCell
            value={analyst.name}
            label="name"
            placeholder="Name"
            muted={muted}
            validate={checkName}
            onSave={(name) => onSave({ name: name.trim() })}
          />
        </td>
        <td className="px-2.5 py-2">
          <EditableCell
            value={analyst.email}
            label="email"
            type="email"
            placeholder="name@example.com"
            muted={muted}
            validate={checkEmail}
            onSave={(email) => onSave({ email: email.trim() })}
          />
        </td>
        <td className="px-2.5 py-2">
          <EditableCell
            value={analyst.aliases.join(", ")}
            label="aliases"
            placeholder="Add aliases"
            muted={muted}
            onSave={(text) => onSave({ aliases: splitAliases(text) })}
          />
        </td>
        <td className="py-3.5">
          <ActiveSwitch analyst={analyst} busy={busy} onToggle={onToggle} />
        </td>
        <td className="px-5 py-2.5 text-right">
          <ConfirmButton size="sm" loading={busy} onConfirm={onDelete} subject={analyst.name} />
        </td>
      </tr>
      {error && (
        <tr className="border-b border-rule">
          <td colSpan={5} className="px-5 pb-3">
            <div role="alert" className="flex flex-wrap items-center gap-3 rounded-md border border-red-line bg-red-bg px-3 py-2 text-[13px] font-semibold text-red">
              <span className="min-w-0 flex-1">{error.message}</span>
              {error.conflict && analyst.active && (
                <Button size="sm" onClick={onToggle} disabled={busy}>
                  Mark inactive
                </Button>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
