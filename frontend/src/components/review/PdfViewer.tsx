import { ChevronLeft, ChevronRight, ExternalLink, MoveHorizontal, SearchX, ZoomIn, ZoomOut } from "lucide-react";
import {
  GlobalWorkerOptions,
  RenderingCancelledException,
  getDocument,
  type PDFDocumentProxy,
  type PageViewport,
  type RenderTask,
} from "pdfjs-dist/legacy/build/pdf.mjs";
// The legacy build carries polyfills for the newest JS the modern build assumes; Vite bundles the worker file.
import workerUrl from "pdfjs-dist/legacy/build/pdf.worker.min.mjs?url";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { findRowBox, type PdfTextItem, type RowBox } from "../../lib/pdfRow";

GlobalWorkerOptions.workerSrc = workerUrl;

/** The meeting whose printed row to find and highlight. */
export interface RowTarget {
  company: string;
  ticker: string | null;
}

// Zoom is relative to "fit width" (1); each step is 25%.
const ZOOM_STEP = 1.25;
const MIN_ZOOM = 0.64;
const MAX_ZOOM = 3.05;
const FRAME_PAD = 8; // the frame's p-2, both sides
const HIT_PAD = 3; // CSS px around the row's text

type Loaded = { url: string; doc: PDFDocumentProxy | null };
type View = { url: string; page: number; viewport: PageViewport };
type Search = { key: string; box: RowBox | null };

function ToolButton({
  label,
  onClick,
  disabled,
  pressed,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  pressed?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onClick}
      className="inline-flex size-7 shrink-0 items-center justify-center rounded-[5px] text-ink transition-colors duration-150 ease-out enabled:hover:bg-white enabled:active:bg-cream disabled:cursor-not-allowed disabled:text-stamp enabled:aria-pressed:bg-white enabled:aria-pressed:text-navy [&>svg]:size-4"
    >
      {children}
    </button>
  );
}

/**
 * The source PDF drawn with pdf.js: one page on a canvas sized to the panel (sharp on high-DPI
 * screens), with the meeting's printed row highlighted and scrolled into view, and its own
 * page, zoom and open-in-a-new-tab controls. `url` is the file itself (versioned, no #page);
 * `openUrl` is what "Open the PDF in a new tab" opens.
 */
export default function PdfViewer({
  url,
  openUrl,
  page,
  target,
}: {
  url: string;
  openUrl: string;
  page: number | null;
  target: RowTarget | null;
}) {
  const frameRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [width, setWidth] = useState(0);
  const [view, setView] = useState<View | null>(null);
  const [renderFailed, setRenderFailed] = useState<string | null>(null);
  const [search, setSearch] = useState<Search | null>(null);

  const doc = loaded?.url === url ? loaded.doc : null;
  const failed = (loaded?.url === url && !loaded.doc) || renderFailed === url;
  const pages = doc?.numPages ?? 0;
  /** A page number kept inside the document once its length is known. */
  const clampPage = (n: number) => Math.max(1, pages ? Math.min(n, pages) : n);
  const targetPage = clampPage(page ?? 1);

  // A new meeting or change opens at its page, fitted to the panel (React's "previous render" pattern).
  const showKey = `${url}|${targetPage}|${target?.company ?? ""}|${target?.ticker ?? ""}`;
  const [shownFor, setShownFor] = useState(showKey);
  const [pageNum, setPageNum] = useState(targetPage);
  const [zoom, setZoom] = useState(1);
  if (shownFor !== showKey) {
    setShownFor(showKey);
    setPageNum(targetPage);
    setZoom(1);
  }
  const shownPage = clampPage(pageNum);

  // Load the document once per URL (a revision or the revised PDF is a new URL).
  useEffect(() => {
    let live = true;
    const task = getDocument({ url });
    task.promise.then(
      (pdf) => live && setLoaded({ url, doc: pdf }),
      () => live && setLoaded({ url, doc: null }),
    );
    return () => {
      live = false;
      task.destroy();
    };
  }, [url]);

  // Fit width follows the frame, which changes between the docked panel and the drawer.
  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;
    const measure = () => setWidth(Math.max(0, frame.clientWidth - FRAME_PAD * 2));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(frame);
    return () => observer.disconnect();
  }, []);

  // Draw the shown page at fit-width x zoom, at the screen's pixel density.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!doc || !canvas || width <= 0) return;
    let live = true;
    let task: RenderTask | null = null;
    doc
      .getPage(shownPage)
      .then((pdfPage) => {
        if (!live) return;
        const fit = width / pdfPage.getViewport({ scale: 1 }).width;
        const viewport = pdfPage.getViewport({ scale: fit * zoom });
        const dpr = window.devicePixelRatio || 1;
        // Draw offscreen, then copy, so a zoom or page change never flashes an empty sheet.
        const scratch = document.createElement("canvas");
        scratch.width = Math.floor(viewport.width * dpr);
        scratch.height = Math.floor(viewport.height * dpr);
        task = pdfPage.render({
          canvas: scratch,
          viewport,
          transform: dpr === 1 ? undefined : [dpr, 0, 0, dpr, 0, 0],
        });
        return task.promise.then(() => {
          if (!live) return;
          canvas.width = scratch.width;
          canvas.height = scratch.height;
          canvas.style.width = `${Math.floor(viewport.width)}px`;
          canvas.style.height = `${Math.floor(viewport.height)}px`;
          canvas.getContext("2d")?.drawImage(scratch, 0, 0);
          setView({ url, page: shownPage, viewport });
        });
      })
      .catch((error: unknown) => {
        if (live && !(error instanceof RenderingCancelledException)) setRenderFailed(url);
      });
    return () => {
      live = false;
      task?.cancel();
    };
  }, [doc, url, shownPage, width, zoom]);

  // Find the meeting's row in the target page's text.
  const company = target?.company ?? null;
  const ticker = target?.ticker ?? null;
  const searchKey = company === null ? null : showKey;
  useEffect(() => {
    if (!doc || company === null || !searchKey) return;
    let live = true;
    doc
      .getPage(targetPage)
      .then((pdfPage) => pdfPage.getTextContent())
      .then(
        (content) => {
          const items = content.items.filter((it) => "str" in it) as PdfTextItem[];
          if (live) setSearch({ key: searchKey, box: findRowBox(items, company, ticker) });
        },
        () => live && setSearch({ key: searchKey, box: null }),
      );
    return () => {
      live = false;
    };
  }, [doc, targetPage, company, ticker, searchKey]);

  const found = searchKey && search?.key === searchKey ? search : null;
  const drawn = view?.url === url ? view : null;
  let hit: { left: number; top: number; width: number; height: number } | null = null;
  if (found?.box && drawn && drawn.page === targetPage && shownPage === targetPage) {
    const { left, bottom, right, top } = found.box;
    const [x1, y1] = drawn.viewport.convertToViewportPoint(left, bottom) as [number, number];
    const [x2, y2] = drawn.viewport.convertToViewportPoint(right, top) as [number, number];
    hit = {
      left: Math.min(x1, x2) - HIT_PAD,
      top: Math.min(y1, y2) - HIT_PAD,
      width: Math.abs(x2 - x1) + HIT_PAD * 2,
      height: Math.abs(y2 - y1) + HIT_PAD * 2,
    };
  }
  const notFound = !!found && !found.box && shownPage === targetPage;

  // Bring the highlighted row into view inside the frame (never the page); other pages start at the top.
  // Only new numbers move the frame, so CR's own scrolling isn't undone on every render.
  const [hitLeft, hitTop, hitWidth, hitHeight] = hit ? [hit.left, hit.top, hit.width, hit.height] : [];
  const drawnKey = drawn ? `${drawn.page}:${drawn.viewport.scale}` : null;
  useEffect(() => {
    const frame = frameRef.current;
    if (!frame || !drawnKey) return;
    if (hitLeft === undefined || hitTop === undefined || hitWidth === undefined || hitHeight === undefined) {
      frame.scrollTo({ top: 0, left: 0 });
      return;
    }
    // The row sits a third of the way down, and centred across when zoomed past the frame.
    const top = hitTop + FRAME_PAD - (frame.clientHeight - hitHeight) / 3;
    const left = hitLeft + FRAME_PAD - Math.max(FRAME_PAD, (frame.clientWidth - hitWidth) / 2);
    frame.scrollTo({ top: Math.max(0, top), left: Math.max(0, left) });
  }, [drawnKey, hitLeft, hitTop, hitWidth, hitHeight]);

  const loading = !failed && !drawn;
  const percent = drawn ? `${Math.round(drawn.viewport.scale * 100)}%` : "—";

  return (
    <div>
      <div className="overflow-hidden rounded-md border border-line bg-cream-2">
        <div role="toolbar" aria-label="PDF page" className="flex items-center gap-0.5 border-b border-line px-1 py-1">
          <ToolButton label="Previous page" disabled={!doc || shownPage <= 1} onClick={() => setPageNum(shownPage - 1)}>
            <ChevronLeft aria-hidden="true" />
          </ToolButton>
          <span className="tabular min-w-[3.25rem] text-center font-heading text-xs font-bold text-ink" aria-live="polite">
            <span className="sr-only">Page </span>
            {doc ? shownPage : "–"}
            <span aria-hidden="true"> / </span>
            <span className="sr-only"> of </span>
            {doc ? pages : "–"}
          </span>
          <ToolButton label="Next page" disabled={!doc || shownPage >= pages} onClick={() => setPageNum(shownPage + 1)}>
            <ChevronRight aria-hidden="true" />
          </ToolButton>
          <span className="mx-1 h-4 w-px shrink-0 bg-line-strong" aria-hidden="true" />
          <ToolButton label="Zoom out" disabled={!doc || zoom <= MIN_ZOOM} onClick={() => setZoom((z) => z / ZOOM_STEP)}>
            <ZoomOut aria-hidden="true" />
          </ToolButton>
          <span className="tabular w-9 text-center text-[11px] font-semibold text-muted">{percent}</span>
          <ToolButton label="Zoom in" disabled={!doc || zoom >= MAX_ZOOM} onClick={() => setZoom((z) => z * ZOOM_STEP)}>
            <ZoomIn aria-hidden="true" />
          </ToolButton>
          <button
            type="button"
            aria-pressed={zoom === 1}
            disabled={!doc}
            onClick={() => setZoom(1)}
            className="inline-flex h-7 shrink-0 items-center gap-1 rounded-[5px] px-1.5 text-xs font-semibold text-ink transition-colors duration-150 ease-out enabled:hover:bg-white disabled:cursor-not-allowed disabled:text-stamp enabled:aria-pressed:bg-white enabled:aria-pressed:text-navy"
          >
            <MoveHorizontal className="size-3.5" aria-hidden="true" />
            Fit width
          </button>
          <a
            href={openUrl}
            target="_blank"
            rel="noreferrer"
            aria-label="Open the PDF in a new tab"
            title="Open the PDF in a new tab"
            className="ml-auto inline-flex size-7 shrink-0 items-center justify-center rounded-[5px] text-blue transition-colors duration-150 ease-out hover:bg-white"
          >
            <ExternalLink className="size-4" aria-hidden="true" />
          </a>
        </div>
        <div
          ref={frameRef}
          className="relative h-[330px] overflow-auto overscroll-contain p-2 [scrollbar-gutter:stable]"
          aria-busy={loading || undefined}
        >
          <div className={`relative mx-auto w-max ${loading || failed ? "invisible" : ""}`}>
            <canvas
              ref={canvasRef}
              role="img"
              aria-label={`Page ${shownPage} of the source PDF${hit ? ", with the meeting's row highlighted" : ""}`}
              className="block bg-white shadow-[0_1px_3px_rgba(24,41,88,0.14)]"
            />
            {hit && (
              <div
                aria-hidden="true"
                className="pdf-hit pointer-events-none absolute rounded-[2px]"
                style={{ left: hit.left, top: hit.top, width: hit.width, height: hit.height }}
              />
            )}
          </div>
          {loading && (
            <div role="status" aria-label="Loading the PDF" className="absolute inset-2 rounded-[3px] bg-white p-4">
              <div className="h-3 w-1/2 rounded-sm bg-skeleton" />
              <div className="mt-3 h-2 w-1/3 rounded-sm bg-skeleton" />
              {Array.from({ length: 9 }, (_, i) => (
                <div key={i} className="mt-3 h-2 rounded-sm bg-skeleton" style={{ width: `${[92, 80, 88, 70, 92, 84, 76, 90, 64][i]}%` }} />
              ))}
            </div>
          )}
          {failed && (
            <p role="alert" className="absolute inset-2 flex items-center justify-center rounded-[3px] bg-white px-6 text-center text-[13px] font-semibold text-ink">
              <span>
                Couldn't show the PDF —{" "}
                <a href={openUrl} target="_blank" rel="noreferrer" className="rounded-sm text-blue underline">
                  open it in a new tab
                </a>
                .
              </span>
            </p>
          )}
        </div>
      </div>
      {notFound && (
        <p role="status" className="mt-1.5 flex items-center gap-1.5 text-xs font-semibold text-muted">
          <SearchX className="size-3.5 shrink-0" aria-hidden="true" />
          Row not found on this page
        </p>
      )}
    </div>
  );
}
