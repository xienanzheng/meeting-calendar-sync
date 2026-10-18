import { Check, CircleAlert, FileText, FileUp, Loader2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import { Link, useNavigate } from "react-router";
import {
  deleteConference,
  errorMessage,
  listConferences,
  listRoster,
  uploadConference,
  type Analyst,
  type ConferenceSummary,
} from "../api";
import { Button, ConfirmButton } from "../components/Button";
import { ErrorNote } from "../components/ErrorNote";
import { Shell } from "../components/Shell";
import { useConfig } from "../lib/config";
import { dateRange, fileSize } from "../lib/format";
import { checkPdf, MAX_UPLOAD_MB } from "../lib/upload";

const MAX_MB = MAX_UPLOAD_MB;

type Loadable<T> = { state: "loading" } | { state: "error"; message: string } | { state: "ready"; data: T };

function ElapsedClock({ since }: { since: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const seconds = Math.max(0, Math.floor((now - since) / 1000));
  return (
    <span className="tabular font-heading font-bold text-navy">
      {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}
    </span>
  );
}

function UploadCard() {
  const navigate = useNavigate();
  const { config } = useConfig();
  const inputRef = useRef<HTMLInputElement>(null);
  const mounted = useRef(true);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [roster, setRoster] = useState<Loadable<Analyst[]>>({ state: "loading" });
  const [defaultIds, setDefaultIds] = useState<number[]>([]);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [extractError, setExtractError] = useState<string | null>(null);
  const [asNew, setAsNew] = useState(false);
  const extracting = startedAt !== null;

  useEffect(() => {
    mounted.current = true;
    listRoster().then(
      (data) => mounted.current && setRoster({ state: "ready", data: data.filter((a) => a.active) }),
      (error) => mounted.current && setRoster({ state: "error", message: errorMessage(error) }),
    );
    return () => {
      mounted.current = false;
    };
  }, []);

  const pick = useCallback((chosen: File | undefined | null) => {
    if (!chosen) return;
    const problem = checkPdf(chosen);
    setFileError(problem);
    setExtractError(null);
    setFile(problem ? null : chosen);
  }, []);

  // A PDF dropped anywhere on the page is taken as the upload instead of the browser opening it.
  useEffect(() => {
    const onDragOver = (event: globalThis.DragEvent) => event.preventDefault();
    const onDrop = (event: globalThis.DragEvent) => {
      event.preventDefault();
      if (!extracting) pick(event.dataTransfer?.files?.[0]);
    };
    window.addEventListener("dragover", onDragOver);
    window.addEventListener("drop", onDrop);
    return () => {
      window.removeEventListener("dragover", onDragOver);
      window.removeEventListener("drop", onDrop);
    };
  }, [extracting, pick]);

  async function extract() {
    if (!file || extracting) return;
    setExtractError(null);
    setStartedAt(Date.now());
    try {
      // By default the server files a re-sent broker PDF as a revision of its conference; "new" opts out.
      const detail = await uploadConference(file, defaultIds, asNew ? "new" : undefined);
      if (mounted.current) navigate(`/conferences/${detail.id}`, { state: { skippedItems: detail.skipped_items } });
    } catch (error) {
      if (mounted.current) setExtractError(errorMessage(error));
    } finally {
      if (mounted.current) setStartedAt(null);
    }
  }

  function toggleDefault(id: number) {
    setDefaultIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));
  }

  const onZoneDrag = (event: DragEvent<HTMLButtonElement>, over: boolean) => {
    event.preventDefault();
    if (!extracting) setDragging(over);
  };

  const readingWith =
    config?.extractor === "fake"
      ? "Reading the PDF with the offline test extractor — a few seconds"
      : "Reading the PDF with Claude — usually 30–60 seconds";

  return (
    <section aria-labelledby="upload-heading" className="rounded-lg border border-line bg-white p-6">
      <h2 id="upload-heading" className="text-lg font-bold text-navy">
        Upload a broker schedule
      </h2>
      <p className="mt-1 text-sm text-muted">
        Claude drafts every meeting from the PDF. Nothing reaches a calendar until you verify it.
      </p>

      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        className="hidden"
        onChange={(event) => {
          pick(event.target.files?.[0]);
          event.target.value = "";
        }}
      />

      {file ? (
        <div className="mt-5 flex items-center gap-3 rounded-md border border-line bg-cream px-4 py-3">
          <FileText className="size-5 shrink-0 text-navy" aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <p className="truncate font-semibold text-ink">{file.name}</p>
            <p className="tabular text-xs font-medium text-muted">{fileSize(file.size)} · PDF</p>
          </div>
          <Button size="sm" disabled={extracting} onClick={() => inputRef.current?.click()}>
            Choose another
          </Button>
          <Button
            disabled={extracting}
            onClick={() => {
              setFile(null);
              setExtractError(null);
            }}
            size="icon"
            aria-label={`Remove ${file.name}`}
            icon={<X className="size-4" aria-hidden="true" />}
          />
        </div>
      ) : (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          onDragOver={(event) => onZoneDrag(event, true)}
          onDragEnter={(event) => onZoneDrag(event, true)}
          onDragLeave={(event) => onZoneDrag(event, false)}
          onDrop={(event) => {
            event.preventDefault();
            event.stopPropagation();
            setDragging(false);
            pick(event.dataTransfer.files?.[0]);
          }}
          className={[
            "mt-5 flex w-full flex-col items-center gap-2 rounded-md border-2 border-dashed px-6 py-9 text-center [&>*]:pointer-events-none",
            "transition-colors duration-150",
            dragging ? "border-navy bg-cream-2" : "border-beige-3 bg-cream hover:border-blue hover:bg-cream-2",
          ].join(" ")}
        >
          <FileUp className="size-7 text-navy" aria-hidden="true" />
          <span className="font-heading text-[15px] font-semibold text-ink">
            Drop a schedule PDF here, or <span className="text-blue underline">choose a file</span>
          </span>
          <span className="text-xs font-medium text-muted">PDF only, up to {MAX_MB} MB</span>
        </button>
      )}
      {fileError && (
        <p role="alert" className="mt-2 flex items-center gap-1.5 text-sm font-semibold text-red">
          <CircleAlert className="size-4 shrink-0" aria-hidden="true" />
          {fileError}
        </p>
      )}

      <fieldset className="mt-6" disabled={extracting}>
        <legend className="font-heading text-sm font-bold text-ink">
          Default colleagues <span className="font-medium text-muted">(optional)</span>
        </legend>
        <p className="mt-0.5 text-[13px] text-muted">Added to every meeting — use for itineraries addressed to one person</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {roster.state === "loading" && (
            <span className="inline-flex items-center gap-2 text-[13px] text-muted">
              <Loader2 className="size-3.5 animate-spin" aria-hidden="true" /> Loading the roster…
            </span>
          )}
          {roster.state === "error" && (
            <span className="text-[13px] font-semibold text-red">Couldn't load the roster: {roster.message}</span>
          )}
          {roster.state === "ready" && roster.data.length === 0 && (
            <span className="text-[13px] text-muted">
              No active colleagues yet.{" "}
              <Link to="/roster" className="font-semibold text-blue underline">
                Add them on the Roster page
              </Link>
              .
            </span>
          )}
          {roster.state === "ready" &&
            roster.data.map((analyst) => {
              const on = defaultIds.includes(analyst.id);
              return (
                <label
                  key={analyst.id}
                  className={[
                    "inline-flex cursor-pointer select-none items-center gap-1.5 rounded-full border px-3 py-1.5 text-[13px] font-semibold",
                    "transition-colors duration-150 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-navy",
                    "has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-50",
                    on ? "border-navy-2 bg-navy-2 text-white" : "border-line bg-white text-ink hover:border-line-strong hover:bg-cream",
                  ].join(" ")}
                >
                  <input type="checkbox" className="sr-only" checked={on} onChange={() => toggleDefault(analyst.id)} />
                  {on && <Check className="size-3.5" strokeWidth={2.5} aria-hidden="true" />}
                  {analyst.name}
                </label>
              );
            })}
        </div>
      </fieldset>

      <div className="mt-6 flex flex-wrap items-center gap-4">
        <Button variant="primary" onClick={extract} disabled={!file} loading={extracting}>
          {extracting ? "Extracting…" : "Extract meetings"}
        </Button>
        {!file && !extracting && <span className="text-[13px] text-muted">Choose a PDF first.</span>}
        <label
          title="When this PDF is a revised schedule for a conference already here, it is normally reviewed as a revision of it."
          className="ml-auto inline-flex cursor-pointer select-none items-center gap-2 text-[13px] font-medium text-ink has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-50">
          <input
            type="checkbox"
            checked={asNew}
            disabled={extracting}
            onChange={(event) => setAsNew(event.target.checked)}
            className="size-4 rounded-sm accent-navy"
          />
          Upload as a new conference instead
          <span className="sr-only">
            {" "}
            (otherwise a revised PDF of a conference already here is reviewed as a revision)
          </span>
        </label>
      </div>

      {extracting && startedAt !== null && (
        <div role="status" className="mt-5 rounded-md border border-line bg-cream px-4 py-3">
          <div className="flex items-center justify-between gap-4 text-sm font-semibold text-ink">
            <span>{readingWith}</span>
            <ElapsedClock since={startedAt} />
          </div>
          <div className="mt-2.5 h-1 overflow-hidden rounded-full bg-beige" aria-hidden="true">
            <div className="progress-sweep h-full w-2/5 rounded-full bg-navy" />
          </div>
        </div>
      )}

      {extractError && !extracting && (
        <div className="mt-5">
          <ErrorNote title="The meetings couldn't be extracted." message={extractError} onRetry={file ? extract : undefined} />
        </div>
      )}
    </section>
  );
}

function hotelLine(c: ConferenceSummary): string {
  // The non-breaking space keeps the dot with the hotel when the line wraps.
  return [c.hotel, c.city].filter((part) => part.trim()).join("\u00a0· ");
}

function CountCell({ value, alert = false }: { value: number; alert?: boolean }) {
  const tone = value === 0 ? "text-muted font-semibold" : alert ? "text-red font-bold" : "text-ink font-bold";
  return <td className={`tabular px-3 py-3 text-right font-heading ${tone}`}>{value}</td>;
}

function ConferenceList() {
  const navigate = useNavigate();
  const [list, setList] = useState<Loadable<ConferenceSummary[]>>({ state: "loading" });
  const [deleting, setDeleting] = useState<number | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const fetchList = useCallback(() => {
    listConferences().then(
      (data) => setList({ state: "ready", data }),
      (error) => setList({ state: "error", message: errorMessage(error) }),
    );
  }, []);

  useEffect(fetchList, [fetchList]);

  const retry = () => {
    setList({ state: "loading" });
    fetchList();
  };

  async function remove(conference: ConferenceSummary) {
    setDeleting(conference.id);
    setDeleteError(null);
    try {
      await deleteConference(conference.id);
      setList((current) =>
        current.state === "ready" ? { state: "ready", data: current.data.filter((c) => c.id !== conference.id) } : current,
      );
    } catch (error) {
      setDeleteError(`${conference.name || "The conference"} wasn't deleted. ${errorMessage(error)}`);
    } finally {
      setDeleting(null);
    }
  }

  const count = list.state === "ready" ? list.data.length : null;

  return (
    <section aria-labelledby="list-heading" className="mt-10">
      <div className="flex items-baseline gap-3">
        <h2 id="list-heading" className="text-lg font-bold text-navy">
          All conferences
        </h2>
        {count !== null && count > 0 && <span className="tabular text-sm font-semibold text-muted">{count}</span>}
      </div>

      {deleteError && (
        <div className="mt-3">
          <ErrorNote title="Delete failed." message={deleteError} />
        </div>
      )}

      {list.state === "loading" && (
        <p role="status" className="mt-4 flex items-center gap-2 text-sm text-muted">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" /> Loading conferences…
        </p>
      )}
      {list.state === "error" && (
        <div className="mt-4">
          <ErrorNote title="Couldn't load the conferences." message={list.message} onRetry={retry} retryLabel="Retry" />
        </div>
      )}
      {list.state === "ready" && list.data.length === 0 && (
        <p className="mt-4 rounded-lg border border-line bg-white px-6 py-10 text-center text-[15px] font-medium text-muted">
          No conferences yet. Upload a broker schedule PDF to start.
        </p>
      )}
      {list.state === "ready" && list.data.length > 0 && (
        <div className="relative mt-4 overflow-x-auto rounded-lg border border-line bg-white">
          <table className="w-full min-w-[860px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-line bg-head text-left font-heading text-[11px] font-bold uppercase tracking-[0.08em] text-muted">
                <th scope="col" className="min-w-52 px-4 py-2.5">Conference</th>
                <th scope="col" className="min-w-44 px-3 py-2.5">Hotel · City</th>
                <th scope="col" className="whitespace-nowrap px-3 py-2.5">Dates</th>
                <th scope="col" className="w-px whitespace-nowrap px-3 py-2.5 text-right">Meetings</th>
                <th scope="col" className="w-px whitespace-nowrap px-3 py-2.5 text-right">Need attention</th>
                <th scope="col" className="w-px whitespace-nowrap px-3 py-2.5 text-right">Verified</th>
                <th scope="col" className="w-px whitespace-nowrap px-3 py-2.5 text-right">Sent</th>
                <th scope="col" className="w-[160px] px-4 py-2.5">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {list.data.map((c) => (
                <tr
                  key={c.id}
                  onClick={() => navigate(`/conferences/${c.id}`)}
                  className="cursor-pointer border-b border-rule transition-colors duration-150 last:border-b-0 hover:bg-cream"
                >
                  <td className="px-4 py-3">
                    <Link
                      to={`/conferences/${c.id}`}
                      onClick={(event) => event.stopPropagation()}
                      className="rounded-sm font-heading text-[15px] font-semibold text-navy hover:underline"
                    >
                      {c.name || "Untitled conference"}
                    </Link>
                    {c.broker && <p className="mt-0.5 text-xs font-medium text-muted">{c.broker}</p>}
                  </td>
                  <td className="px-3 py-3 text-muted">{hotelLine(c) || "—"}</td>
                  <td className="tabular whitespace-nowrap px-3 py-3 font-medium">{dateRange(c.first_date, c.last_date)}</td>
                  <CountCell value={c.counts.total} />
                  <CountCell value={c.counts.needs_attention} alert />
                  <CountCell value={c.counts.verified} />
                  <CountCell value={c.counts.sent} />
                  <td className="px-4 py-3 text-right">
                    <ConfirmButton
                      size="sm"
                      loading={deleting === c.id}
                      disabled={deleting !== null && deleting !== c.id}
                      onConfirm={() => remove(c)}
                      subject={c.name || "Untitled conference"}
                      title="Deletes the conference and its meetings here. Calendar entries already sent are not touched."
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function ConferencesPage() {
  return (
    <Shell>
      <div className="mx-auto max-w-[1100px] px-7 pb-16 pt-9">
        <h1 className="text-[28px] font-bold leading-tight text-navy">Conferences</h1>
        <p className="mt-1.5 text-[15px] text-muted">
          Upload a broker's schedule and check each meeting against the PDF. Verifying a meeting puts it on the right
          colleagues' calendars.
        </p>
        <div className="mt-7">
          <UploadCard />
        </div>
        <ConferenceList />
      </div>
    </Shell>
  );
}
