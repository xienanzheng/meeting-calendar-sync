import { Calendar, CalendarCheck, CircleAlert, Copy, Download, ExternalLink, Loader2, LogIn, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import {
  errorMessage,
  graphLogin,
  graphStatus,
  icsUrl,
  icsZipUrl,
  type ConferenceDetail,
  type GraphLoginStart,
  type GraphStatus,
} from "../../api";
import { useConfig } from "../../lib/config";
import { Button } from "../Button";
import { Popover } from "../Popover";

/** The last sync message from a mutation response, stamped so a repeat message shows again. */
export interface SyncNote {
  message: string;
  ok: number;
  failed: number;
  at: number;
}

const ROUTES = { ics: ".ics files", graph: "Outlook (Microsoft Graph)" } as const;
const NOTE_MS = 6000;

/** Calendar entries the server has written for each colleague (the ones with a file to download). */
function calendarFiles(detail: ConferenceDetail) {
  const out = new Map<number, { id: number; name: string; count: number }>();
  for (const m of detail.meetings) {
    for (const a of [...m.attendees, ...m.removed]) {
      if (a.sync === "not_sent") continue;
      const entry = out.get(a.analyst_id) ?? { id: a.analyst_id, name: a.name, count: 0 };
      entry.count += 1;
      out.set(a.analyst_id, entry);
    }
  }
  return [...out.values()].sort((a, b) => a.name.localeCompare(b.name));
}

function onCalendarCount(detail: ConferenceDetail): number {
  return detail.meetings
    .filter((m) => m.review_state !== "cancelled")
    .reduce((n, m) => n + m.attendees.filter((a) => a.sync === "sent").length, 0);
}

type Login =
  | { phase: "idle" }
  | { phase: "starting" }
  | { phase: "code"; start: GraphLoginStart }
  | { phase: "error"; message: string }
  | { phase: "done" };

function GraphSignIn({ login, onStart }: { login: Login; onStart: () => void }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="p-4">
      <h2 className="font-heading text-[15px] font-bold text-navy">Sign in to Microsoft</h2>
      <p className="mt-1 text-[13px] text-muted">
        Sign in with your own account. Verified meetings then go straight into each colleague's Outlook calendar through
        your delegate access.
      </p>
      {login.phase === "starting" && (
        <p role="status" className="mt-3 flex items-center gap-2 text-[13px] font-semibold text-ink">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" /> Getting a sign-in code…
        </p>
      )}
      {login.phase === "code" && (
        <div className="mt-3 space-y-3">
          <p className="text-[13px] font-semibold text-ink">
            1.{" "}
            <a
              href={login.start.verification_uri}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 rounded-sm text-blue underline"
            >
              Open {login.start.verification_uri.replace(/^https?:\/\//, "")}
              <ExternalLink className="size-3" aria-hidden="true" />
            </a>
          </p>
          <div>
            <p className="text-[13px] font-semibold text-ink">2. Enter this code</p>
            <div className="mt-1.5 flex items-center gap-2">
              <code className="tabular rounded-md border border-line bg-cream px-3 py-1.5 font-heading text-xl font-bold tracking-[0.12em] text-navy">
                {login.start.user_code}
              </code>
              <Button
                size="sm"
                icon={<Copy className="size-3.5" aria-hidden="true" />}
                onClick={() => {
                  navigator.clipboard?.writeText(login.start.user_code).then(
                    () => setCopied(true),
                    () => setCopied(false),
                  );
                }}
              >
                {copied ? "Copied" : "Copy"}
              </Button>
            </div>
          </div>
          <p role="status" className="flex items-center gap-2 text-[13px] text-muted">
            <Loader2 className="size-3.5 animate-spin" aria-hidden="true" /> Waiting for you to finish signing in…
          </p>
        </div>
      )}
      {login.phase === "error" && (
        <div role="alert" className="mt-3 rounded-md border border-red-line bg-red-bg px-3 py-2.5 text-[13px] font-semibold text-red">
          <p>{login.message}</p>
          <Button size="sm" className="mt-2" onClick={onStart}>
            Try again
          </Button>
        </div>
      )}
      {login.phase === "done" && (
        <p role="status" className="mt-3 text-[13px] font-semibold text-green">
          Signed in. Calendars are updating.
        </p>
      )}
    </div>
  );
}

function CalendarFiles({ detail }: { detail: ConferenceDetail }) {
  const files = calendarFiles(detail);
  return (
    <div className="p-4">
      <h2 className="font-heading text-[15px] font-bold text-navy">Calendar files</h2>
      <p className="mt-1 text-[13px] text-muted">Open each file in Outlook to add it to that colleague's calendar.</p>
      {files.length === 0 ? (
        <p className="mt-3 rounded-md bg-cream px-3 py-2.5 text-[13px] font-medium text-ink">
          Nothing is on a calendar yet. Verify a meeting and its colleagues' files appear here.
        </p>
      ) : (
        <>
          <ul className="mt-3 divide-y divide-rule rounded-md border border-line">
            {files.map((f) => (
              <li key={f.id}>
                <a
                  href={icsUrl(detail.id, f.id)}
                  download
                  className="flex items-center gap-2.5 px-3 py-2 text-sm font-semibold text-ink transition-colors duration-150 hover:bg-cream"
                >
                  <Download className="size-4 shrink-0 text-blue" aria-hidden="true" />
                  <span className="min-w-0 flex-1 truncate">{f.name}</span>
                  <span className="tabular shrink-0 text-xs font-medium text-muted">
                    {f.count} {f.count === 1 ? "meeting" : "meetings"}
                  </span>
                </a>
              </li>
            ))}
          </ul>
          <a
            href={icsZipUrl(detail.id)}
            download
            className="mt-3 inline-flex h-8 items-center gap-1.5 rounded-md bg-navy px-3 font-heading text-[13px] font-bold text-white transition-colors duration-150 hover:bg-navy-2"
          >
            <Download className="size-3.5" aria-hidden="true" />
            Download all (.zip)
          </a>
        </>
      )}
    </div>
  );
}

/**
 * The calendar sync line in the top bar: what's on calendars, what failed (with Retry), the Microsoft
 * sign-in when Outlook is the route, and per-colleague .ics downloads when files are. It always names
 * the active route, and briefly shows the message from the latest change.
 */
export function SyncStatus({
  detail,
  note,
  onRetry,
}: {
  detail: ConferenceDetail;
  note: SyncNote | null;
  onRetry: () => Promise<void>;
}) {
  const { config } = useConfig();
  const sink = config?.calendar_sink ?? "ics";
  const [polled, setPolled] = useState<GraphStatus | null>(null);
  const graph = polled ?? config?.graph ?? null;
  const [login, setLogin] = useState<Login>({ phase: "idle" });
  const [retrying, setRetrying] = useState(false);
  const [localNote, setLocalNote] = useState<SyncNote | null>(null);
  const [expired, setExpired] = useState<number | null>(null);
  const anchor = useRef<HTMLButtonElement>(null);
  const popId = `sync-${detail.id}`;

  // The latest message (from a change, or a failed Retry here) stays for ~6 s.
  const latest = !note || (localNote && localNote.at > note.at) ? localNote : note;
  const flash = latest && latest.at !== expired ? latest.message : null;
  useEffect(() => {
    if (!latest) return;
    const at = latest.at;
    const timer = window.setTimeout(() => setExpired(at), NOTE_MS);
    return () => window.clearTimeout(timer);
  }, [latest]);

  // While a device-code sign-in is open, poll every 3 s; once signed in, push what's waiting.
  useEffect(() => {
    if (login.phase !== "code") return;
    const timer = window.setInterval(() => {
      graphStatus().then(
        (status) => {
          setPolled(status);
          if (status.signed_in) {
            setLogin({ phase: "done" });
            onRetry().catch(() => undefined);
          } else if (status.error && !status.pending) {
            setLogin({ phase: "error", message: status.error });
          }
        },
        () => undefined, // a missed poll is retried on the next tick
      );
    }, 3000);
    return () => window.clearInterval(timer);
  }, [login.phase, onRetry]);

  function startLogin() {
    if (login.phase === "starting" || login.phase === "code") return;
    setLogin({ phase: "starting" });
    graphLogin().then(
      (start) => setLogin({ phase: "code", start }),
      (error) => setLogin({ phase: "error", message: errorMessage(error) }),
    );
  }

  async function retry() {
    setRetrying(true);
    try {
      await onRetry();
    } catch (error) {
      setLocalNote({ message: errorMessage(error), ok: 0, failed: 0, at: Date.now() });
    } finally {
      setRetrying(false);
    }
  }

  const needsSignIn = sink === "graph" && !graph?.signed_in;
  const failed = detail.counts.failed;
  const pending = detail.counts.pending_actions;
  const onCalendars = onCalendarCount(detail);
  const route = `via ${ROUTES[sink]}`;

  let icon = <CalendarCheck className="size-4 text-beige" aria-hidden="true" />;
  let title = `${onCalendars} on calendars`;
  let sub = route;
  let action: "retry" | "sync" | null = null;
  if (needsSignIn) {
    icon = <LogIn className="size-4 text-beige" aria-hidden="true" />;
    title = "Sign in to Microsoft";
    sub = pending > 0 ? `${pending} ${pending === 1 ? "update" : "updates"} waiting for Outlook` : route;
  } else if (failed > 0) {
    icon = <CircleAlert className="size-4 text-red-on-navy" aria-hidden="true" />;
    title = `${failed} failed —`;
    sub = `${onCalendars} on calendars · ${route}`;
    action = "retry";
  } else if (pending > 0) {
    icon = <RefreshCw className="size-4 text-amber-on-navy" aria-hidden="true" />;
    title = `${pending} to update —`;
    action = "sync";
  } else if (onCalendars === 0) {
    icon = <Calendar className="size-4 text-white/75" aria-hidden="true" />;
    title = "Nothing on calendars yet";
  }

  return (
    <div className="relative flex shrink-0 items-center gap-1.5">
      <button
        ref={anchor}
        type="button"
        popoverTarget={popId}
        onClick={needsSignIn ? startLogin : undefined}
        className={[
          "flex items-center gap-2 rounded-md px-2 py-1 text-left transition-colors duration-150 hover:bg-navy-2",
          needsSignIn ? "border border-white/35" : "",
        ].join(" ")}
      >
        {icon}
        <span className="leading-tight">
          <span className={`tabular block whitespace-nowrap text-[13px] font-semibold ${failed > 0 && !needsSignIn ? "text-red-on-navy" : "text-white"}`}>
            {title}
          </span>
          <span className="block whitespace-nowrap text-[11px] font-medium text-white/75">{sub}</span>
        </span>
      </button>
      {action && (
        <Button
          variant="ghost"
          size="sm"
          loading={retrying}
          icon={<RefreshCw className="size-3.5" aria-hidden="true" />}
          onClick={retry}
        >
          {action === "retry" ? "Retry" : "Sync now"}
        </Button>
      )}

      {/* Always mounted so screen readers hear each new message. */}
      <div role="status" aria-live="polite" className="pointer-events-none absolute right-0 top-full z-40 mt-3">
        {flash && (
          <p className="w-max max-w-[320px] rounded-md bg-ink px-3 py-2 text-xs font-semibold text-white shadow-[0_4px_12px_rgba(24,41,88,0.25)]">
            {flash}
          </p>
        )}
      </div>

      <Popover id={popId} anchor={anchor} label={needsSignIn ? "Sign in to Microsoft" : "Calendar status"}>
        {needsSignIn || login.phase === "done" ? (
          <GraphSignIn login={login} onStart={startLogin} />
        ) : sink === "graph" ? (
          <div className="p-4">
            <h2 className="font-heading text-[15px] font-bold text-navy">Outlook calendars</h2>
            <p className="mt-1 text-[13px] text-muted">
              Signed in as {graph?.account ?? "your account"}. Verified meetings go straight into each colleague's
              Outlook calendar.
            </p>
          </div>
        ) : (
          <CalendarFiles detail={detail} />
        )}
      </Popover>
    </div>
  );
}
