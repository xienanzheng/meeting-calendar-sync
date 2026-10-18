import { CheckCheck, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";
import {
  applyRevision,
  confirmReady,
  discardRevision,
  errorMessage,
  getConference,
  listRoster,
  patchConference,
  retrySync,
  revisionAsNewConference,
  uploadRevision,
  type Analyst,
  type ConferenceDetail,
  type Counts,
  type Meeting,
} from "../api";
import { Button } from "../components/Button";
import { ErrorNote } from "../components/ErrorNote";
import { Note } from "../components/Note";
import { Shell } from "../components/Shell";
import { AddMeetingRow } from "../components/review/AddMeetingRow";
import { ColleagueRail, ColleagueSelect } from "../components/review/ColleagueRail";
import { ConferenceContext } from "../components/review/ConferenceContext";
import { RevisionReview } from "../components/review/RevisionReview";
import { RevisionStrip, type RevisionBusy } from "../components/review/RevisionStrip";
import { SourcePanel } from "../components/review/SourcePanel";
import { StatusChips } from "../components/review/StatusChips";
import { SyncStatus, type SyncNote } from "../components/review/SyncStatus";
import { Timetable, type SelectVia } from "../components/review/Timetable";
import { viewerZone } from "../lib/format";
import { defaultAccepted, toggleAccepted } from "../lib/revision";
import {
  colleaguesIn,
  filterMeetings,
  groupByDate,
  selectionKey,
  statusCounts,
  unmatchedNames,
  type Selection,
  type StatusFilter,
} from "../lib/review";
import { useConference } from "../lib/useConference";
import { useMediaQuery } from "../lib/useMediaQuery";

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** The rows in timetable order (days, then start time) for a rail selection and status chip. */
function rowsFor(meetings: Meeting[], selection: Selection, status: StatusFilter): Meeting[] {
  return groupByDate(filterMeetings(meetings, selection, status)).flatMap((g) => g.meetings);
}

/** The panel opens on the first meeting that needs attention, else the first row. */
function pickDefault(rows: Meeting[]): number | null {
  return (rows.find((m) => m.review_state === "needs_attention") ?? rows[0])?.id ?? null;
}

const EMPTY_FILTER: Record<StatusFilter, string> = {
  all: "No meetings",
  needs_attention: "Nothing needs attention",
  ready: "No drafts are ready to verify",
  verified: "Nothing is verified and waiting for calendars",
  sent: "Nothing is on calendars yet",
};

/** The conference totals as a compact two-line block, in step with the context and sync status beside it. */
function Totals({ counts }: { counts: Counts }) {
  const num = "tabular font-heading font-bold";
  return (
    <p className="whitespace-nowrap leading-tight max-[1439px]:hidden">
      <span className="block text-[13px] font-semibold text-white">
        <span className={`${num} text-[15px]`}>{counts.total}</span> meetings ·{" "}
        <span className={`${num} text-[15px] ${counts.needs_attention > 0 ? "text-red-on-navy" : ""}`}>{counts.needs_attention}</span>{" "}
        need attention
      </span>
      <span className="block text-[11px] font-medium text-white/75">
        <span className={num}>{counts.verified}</span> verified · <span className={num}>{counts.sent}</span> sent
      </span>
    </p>
  );
}

const RAIL_GRID =
  "relative grid min-h-0 flex-1 overflow-hidden grid-cols-[250px_minmax(0,1fr)_400px] max-panel:grid-cols-[250px_minmax(0,1fr)] max-rail:grid-cols-1";

function Skeleton() {
  const block = "rounded-md bg-skeleton";
  return (
    <div role="status" aria-label="Loading the conference" className={`${RAIL_GRID} h-full`}>
      <div className="space-y-2 border-r border-line bg-cream-2 px-6 py-6 max-rail:hidden">
        {Array.from({ length: 7 }, (_, i) => (
          <div key={i} className={`${block} h-9`} />
        ))}
      </div>
      <div className="px-7 pt-[22px]">
        <div className={`${block} h-8 w-64`} />
        <div className={`${block} mt-4 h-8 w-[420px] max-w-full`} />
        <div className={`${block} mt-7 h-4 w-48`} />
        <div className="mt-2 overflow-hidden rounded-lg border border-line bg-white">
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="flex gap-4 border-b border-rule px-3 py-4 last:border-b-0">
              <div className={`${block} h-9 w-20`} />
              <div className={`${block} h-9 flex-1`} />
              <div className={`${block} h-9 w-28`} />
            </div>
          ))}
        </div>
      </div>
      <div className="border-l border-line bg-white px-[22px] py-5 max-panel:hidden">
        <div className={`${block} h-4 w-56`} />
        <div className={`${block} mt-3 h-[346px]`} />
      </div>
    </div>
  );
}

export function ReviewPage() {
  const params = useParams();
  const id = Number(params.id);
  if (!Number.isInteger(id) || id <= 0) return <Missing />;
  // A fresh component per conference, so selection and filters never carry over.
  return <Review key={id} id={id} />;
}

function Missing() {
  return (
    <Shell>
      <div className="mx-auto max-w-[1100px] px-7 pb-16 pt-9">
        <h1 className="text-[28px] font-bold leading-tight text-navy">This conference doesn't exist.</h1>
        <p className="mt-1.5 text-[15px] text-muted">
          It may have been deleted.{" "}
          <Link to="/" className="rounded-sm font-semibold text-blue underline">
            Back to conferences
          </Link>
        </p>
      </div>
    </Shell>
  );
}

function Review({ id }: { id: number }) {
  const location = useLocation();
  const navigate = useNavigate();
  const skipped = Number((location.state as { skippedItems?: number } | null)?.skippedItems ?? 0);
  const { detail, error, apply, reload } = useConference(id);
  const drawer = useMediaQuery("(max-width: 1280px)");
  const viewerTz = useMemo(() => viewerZone(), []);

  const [selection, setSelection] = useState<Selection>({ kind: "all" });
  const [status, setStatus] = useState<StatusFilter>("all");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [note, setNote] = useState<SyncNote | null>(null);
  const [roster, setRoster] = useState<Analyst[] | null>(null);
  const [banner, setBanner] = useState<{ title: string; message: string } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [verifyingAll, setVerifyingAll] = useState(false);

  const [reviewOpen, setReviewOpen] = useState(false);
  const [accepted, setAccepted] = useState<Set<string>>(() => new Set());
  const [changeId, setChangeId] = useState<string | null>(null);
  const [revBusy, setRevBusy] = useState<RevisionBusy>(null);
  const [applying, setApplying] = useState(false);
  const [seenRevision, setSeenRevision] = useState<number | null>(null);

  const headingRef = useRef<HTMLHeadingElement>(null);
  const returnTo = useRef<HTMLElement | null>(null);
  const focusPanel = useRef(false);

  useEffect(() => {
    let live = true;
    listRoster().then(
      (list) => live && setRoster(list),
      () => live && setRoster([]),
    );
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    document.title = detail ? `${detail.name || "Untitled conference"} · Meeting Calendar Sync` : "Meeting Calendar Sync";
    return () => {
      document.title = "Meeting Calendar Sync";
    };
  }, [detail]);

  /** Every change goes through here: fresh detail in, and its sync message into the status line. */
  const run = useCallback(
    async (promise: Promise<ConferenceDetail>) => {
      const next = await apply(promise);
      if (next.last_sync) setNote({ ...next.last_sync, at: Date.now() });
      return next;
    },
    [apply],
  );

  const retry = useCallback(async () => {
    const result = await retrySync(id);
    await apply(getConference(id));
    const message = result.failed_count
      ? `${plural(result.failed_count, "calendar update")} failed again. Check each colleague's line in the panel.`
      : result.ok_count
        ? `Updated ${plural(result.ok_count, "calendar entry", "calendar entries")}.`
        : "Calendars are up to date.";
    setNote({ ok: result.ok_count, failed: result.failed_count, message, at: Date.now() });
  }, [id, apply]);

  // ---------- derived ----------
  const meetings = useMemo(() => detail?.meetings ?? [], [detail]);
  const colleagues = useMemo(() => colleaguesIn({ meetings }), [meetings]);
  const unmatched = useMemo(() => unmatchedNames({ meetings }), [meetings]);
  const pending = detail?.pending_revision ?? null;

  // State that follows fresh detail is adjusted during render (React's "previous render" pattern), not in effects.
  // A colleague who no longer appears (e.g. taken off their only meeting) falls back to All.
  const known = ["all", ...colleagues.map((c) => `c:${c.id}`), ...unmatched.map((u) => `u:${u.name}`)];
  if (detail && !known.includes(selectionKey(selection))) setSelection({ kind: "all" });
  // A newly arrived revision opens its review with every change ticked; an applied or discarded one closes it.
  if ((pending?.id ?? null) !== seenRevision) {
    setSeenRevision(pending?.id ?? null);
    setAccepted(pending ? defaultAccepted(pending) : new Set());
    setChangeId(pending?.changes[0]?.id ?? null);
    setReviewOpen(!!pending && pending.changes.length > 0);
  }

  const inSelection = useMemo(() => filterMeetings(meetings, selection, "all"), [meetings, selection]);
  const counts = useMemo(() => statusCounts(inSelection), [inSelection]);
  const groups = useMemo(() => groupByDate(filterMeetings(meetings, selection, status)), [meetings, selection, status]);
  const rows = useMemo(() => groups.flatMap((g) => g.meetings), [groups]);
  const readyIds = rows.filter((m) => m.review_state === "ready").map((m) => m.id);
  const selected = meetings.find((m) => m.id === selectedId) ?? null;
  const total = statusCounts(meetings).all;
  // Keep the selected meeting while it exists; otherwise open the default one.
  if (detail && !selected) {
    const fallback = pickDefault(rows);
    if (fallback !== selectedId) setSelectedId(fallback);
  }

  // Opening the drawer moves focus into it; closing it returns focus to the row.
  useEffect(() => {
    if (drawer && drawerOpen && focusPanel.current) {
      focusPanel.current = false;
      headingRef.current?.focus();
    }
  }, [drawer, drawerOpen, selectedId]);

  // ---------- actions ----------
  function changeSelection(next: Selection) {
    setSelection(next);
    const visible = rowsFor(meetings, next, status);
    if (!visible.some((m) => m.id === selectedId)) setSelectedId(pickDefault(visible));
  }

  function changeStatus(next: StatusFilter) {
    setStatus(next);
    const visible = rowsFor(meetings, selection, next);
    if (!visible.some((m) => m.id === selectedId)) setSelectedId(pickDefault(visible));
  }

  function selectRow(meetingId: number, via: SelectVia) {
    setSelectedId(meetingId);
    if (drawer) {
      returnTo.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      focusPanel.current = via === "keyboard" || !drawerOpen;
      setDrawerOpen(true);
    }
  }

  const closeDrawer = useCallback(() => {
    setDrawerOpen(false);
    returnTo.current?.focus();
  }, []);

  // Esc closes the drawer from anywhere on the page, unless a popover is taking it.
  useEffect(() => {
    if (!drawer || !drawerOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.defaultPrevented && !document.querySelector(":popover-open")) closeDrawer();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawer, drawerOpen, closeDrawer]);

  async function verifyAll() {
    setVerifyingAll(true);
    setBanner(null);
    try {
      await run(confirmReady(id, readyIds));
    } catch (err) {
      setBanner({ title: "The ready meetings weren't verified.", message: errorMessage(err) });
    } finally {
      setVerifyingAll(false);
    }
  }

  async function uploadRevised(file: File) {
    setUploading(true);
    setBanner(null);
    try {
      await run(uploadRevision(id, file));
    } catch (err) {
      setBanner({ title: `${file.name} couldn't be read as a revision.`, message: errorMessage(err) });
    } finally {
      setUploading(false);
    }
  }

  async function revisionAction(kind: Exclude<RevisionBusy, null>, action: () => Promise<unknown>) {
    setRevBusy(kind);
    setBanner(null);
    try {
      await action();
    } catch (err) {
      const titles = {
        accept: "The revision wasn't applied.",
        discard: "The revision wasn't discarded.",
        separate: "The revision wasn't split off.",
      };
      setBanner({ title: titles[kind], message: errorMessage(err) });
    } finally {
      setRevBusy(null);
    }
  }

  async function applyTicked() {
    if (!pending) return;
    setApplying(true);
    setBanner(null);
    try {
      await run(applyRevision(pending.id, [...accepted]));
    } catch (err) {
      setBanner({ title: "The changes weren't applied.", message: errorMessage(err) });
    } finally {
      setApplying(false);
    }
  }

  // ---------- render ----------
  if (!detail) {
    if (error?.status === 404) return <Missing />;
    return (
      <Shell scroll={!!error}>
        {error ? (
          <div className="mx-auto max-w-[1100px] px-7 pt-9">
            <ErrorNote title="Couldn't load this conference." message={error.detail} onRetry={() => reload().catch(() => undefined)} retryLabel="Retry" />
          </div>
        ) : (
          <Skeleton />
        )}
      </Shell>
    );
  }

  const entry = selection.kind === "colleague" ? colleagues.find((c) => c.id === selection.id) : undefined;
  const days = new Set(inSelection.filter((m) => m.review_state !== "cancelled" && m.date).map((m) => m.date)).size;
  const heading = entry?.name ?? (selection.kind === "unmatched" ? selection.name : "All colleagues");
  const summary =
    selection.kind === "unmatched" ? (
      <>
        {counts.all === 1 ? "1 meeting prints" : `${counts.all} meetings print`} this name, but it isn't on the roster. Add it
        as an alias on the{" "}
        <Link to="/roster" className="rounded-sm font-semibold text-blue underline">
          Roster
        </Link>{" "}
        page, or dismiss it on each meeting.
      </>
    ) : (
      [
        plural(counts.all, "meeting"),
        plural(days, "day"),
        entry ? `what lands in ${entry.email}` : plural(colleagues.length, "colleague"),
      ].join(" · ")
    );
  const railProps = { colleagues, unmatched, total, selection, onSelect: changeSelection };
  const revisionSource = reviewOpen && pending ? { revision: pending, change: pending.changes.find((c) => c.id === changeId) ?? null } : null;

  return (
    <Shell
      scroll={false}
      context={
        <ConferenceContext
          detail={detail}
          uploading={uploading}
          onRename={async (name) => {
            await run(patchConference(id, { name }));
          }}
          onTimezone={async (timezone) => {
            await run(patchConference(id, { timezone }));
          }}
          onUploadRevision={uploadRevised}
          onUploadProblem={(message) => setBanner({ title: "That file can't be used as a revision.", message })}
        />
      }
      actions={
        <>
          <Totals counts={detail.counts} />
          <SyncStatus detail={detail} note={note} onRetry={retry} />
          {readyIds.length > 0 && (
            <Button
              variant="beige"
              loading={verifyingAll}
              onClick={verifyAll}
              icon={<CheckCheck className="size-4" aria-hidden="true" />}
              title="Verifies every draft without problems in the current view; they go straight to calendars"
            >
              Verify all ready ({readyIds.length})
            </Button>
          )}
        </>
      }
    >
      <div className="flex h-full min-h-0 flex-col">
        {pending && (
          <RevisionStrip
            revision={pending}
            reviewing={reviewOpen}
            busy={revBusy}
            onToggleReview={() => setReviewOpen((open) => !open)}
            onAcceptAll={() => revisionAction("accept", () => run(applyRevision(pending.id, null)))}
            onDiscard={() => revisionAction("discard", () => run(discardRevision(pending.id)))}
            onKeepSeparate={() =>
              revisionAction("separate", async () => {
                const created = await revisionAsNewConference(pending.id);
                navigate(`/conferences/${created.id}`);
              })
            }
          />
        )}
        <div className={RAIL_GRID}>
          <aside className="overflow-y-auto border-r border-line bg-cream-2 max-rail:hidden">
            <ColleagueRail {...railProps} />
          </aside>

          <section aria-label="Itinerary" className="itinerary min-w-0 overflow-y-auto px-7 pb-10 pt-[22px] max-rail:px-4">
            {banner && (
              <div className="mb-4">
                <ErrorNote title={banner.title} message={banner.message} onDismiss={() => setBanner(null)} />
              </div>
            )}
            {skipped > 0 && (
              <Note tone="amber" role="note" icon={<TriangleAlert aria-hidden="true" />} className="mb-4">
                Claude skipped {plural(skipped, "unreadable row")} — check the PDF.
              </Note>
            )}

            {revisionSource ? (
              <RevisionReview
                revision={revisionSource.revision}
                meetings={meetings}
                accepted={accepted}
                selectedChangeId={changeId}
                applying={applying}
                onToggle={(cid) => setAccepted((set) => toggleAccepted(set, cid))}
                onSetAll={(on) => setAccepted(on ? defaultAccepted(revisionSource.revision) : new Set())}
                onSelectChange={(cid) => {
                  setChangeId(cid);
                  if (drawer) {
                    focusPanel.current = false;
                    setDrawerOpen(true);
                  }
                }}
                onApply={applyTicked}
                onClose={() => setReviewOpen(false)}
              />
            ) : (
              <>
                <div className="flex flex-wrap items-baseline gap-x-3.5 gap-y-1">
                  <h1 className="text-[28px] font-bold leading-tight text-navy">{heading}</h1>
                  <p className="text-sm text-muted">{summary}</p>
                </div>
                <div className="mt-3.5 rail:hidden">
                  <ColleagueSelect {...railProps} />
                </div>
                <div className="mb-[18px] mt-3.5">
                  <StatusChips counts={counts} value={status} onChange={changeStatus} />
                </div>

                {meetings.length === 0 ? (
                  <p className="rounded-lg border border-line bg-white px-6 py-8 text-[15px] font-medium text-ink">
                    No meetings were found in this PDF. Add them by hand, or check the PDF.
                  </p>
                ) : rows.length === 0 ? (
                  <div className="rounded-lg border border-line bg-white px-6 py-8">
                    <p className="text-[15px] font-medium text-ink">
                      {EMPTY_FILTER[status]}
                      {selection.kind === "all" ? "" : ` for ${heading}`}.
                    </p>
                    {status !== "all" && (
                      <Button size="sm" className="mt-3" onClick={() => changeStatus("all")}>
                        Show all {plural(counts.all, "meeting")}
                      </Button>
                    )}
                  </div>
                ) : (
                  <Timetable
                    groups={groups}
                    selection={selection}
                    selectedId={selectedId}
                    hotelTz={detail.timezone}
                    viewerTz={viewerTz}
                    onSelect={selectRow}
                  />
                )}
                <AddMeetingRow
                  cid={id}
                  knownIds={meetings.map((m) => m.id)}
                  roster={roster}
                  defaultDate={detail.first_date}
                  defaultColleague={selection.kind === "colleague" ? selection.id : null}
                  startOpen={meetings.length === 0}
                  run={run}
                  onAdded={(meetingId) => {
                    if (meetingId !== null) setSelectedId(meetingId);
                  }}
                />
              </>
            )}
          </section>

          <SourcePanel
            detail={detail}
            meeting={selected}
            selection={selection}
            roster={roster}
            run={run}
            revisionSource={revisionSource}
            drawer={drawer}
            open={drawerOpen}
            onClose={closeDrawer}
            headingRef={headingRef}
          />
        </div>
      </div>
    </Shell>
  );
}
