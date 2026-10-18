import { CalendarDays, CircleAlert, Info, ScanText } from "lucide-react";
import type { ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router";
import type { AppConfig } from "../api";
import { useConfig } from "../lib/config";
import { WoodlineMark } from "./WoodlineMark";

export interface ShellProps {
  /** Page context after the product name; the Review page puts the conference, hotel, dates and timezone here. */
  context?: ReactNode;
  /** Right-most controls in the bar, e.g. the beige "Send N to calendars" button. */
  actions?: ReactNode;
  /** False for pages whose columns scroll on their own (Review): no page scroll, no reserved scrollbar gutter. */
  scroll?: boolean;
  children?: ReactNode;
}

const EXTRACTOR_LABELS: Record<string, string> = {
  anthropic: "Claude · anthropic",
  "claude-code": "Claude · claude-code",
  foundry: "Claude · foundry",
  fake: "Offline test extractor",
};

const SINK_LABELS: Record<string, string> = {
  ics: "Calendar · .ics",
  graph: "Calendar · Outlook",
};

function navClass(active: boolean): string {
  return [
    "rounded-sm py-1 underline-offset-[7px] decoration-2 transition-colors duration-150",
    active ? "text-white underline decoration-beige" : "text-white/75 hover:text-white hover:underline hover:decoration-white/40",
  ].join(" ");
}

function Badge({ icon, children, title }: { icon: ReactNode; children: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full bg-navy-2 px-2.5 py-1 text-xs font-semibold text-white"
    >
      {icon}
      {children}
    </span>
  );
}

function ConfigBadges({ config, error }: { config: AppConfig | null; error: string | null }) {
  if (error) {
    return (
      <Badge icon={<CircleAlert className="size-3.5 text-red-on-navy" aria-hidden="true" />} title={error}>
        Server not reachable
      </Badge>
    );
  }
  if (!config) return null;
  const graph = config.calendar_sink === "graph" ? config.graph : null;
  const sinkTitle = graph
    ? graph.signed_in
      ? `Writing to Outlook through Microsoft Graph as ${graph.account ?? "the signed-in account"}`
      : "Writing to Outlook through Microsoft Graph (not signed in)"
    : "Sending produces .ics files to download and import";
  return (
    <>
      <Badge
        icon={<ScanText className="size-3.5 text-beige" aria-hidden="true" />}
        title={`Extractor: ${config.extractor}, model ${config.model}`}
      >
        {EXTRACTOR_LABELS[config.extractor] ?? `Extractor · ${config.extractor}`}
      </Badge>
      <Badge icon={<CalendarDays className="size-3.5 text-beige" aria-hidden="true" />} title={sinkTitle}>
        {SINK_LABELS[config.calendar_sink] ?? `Calendar · ${config.calendar_sink}`}
      </Badge>
    </>
  );
}

export function Shell({ context, actions, scroll = true, children }: ShellProps) {
  const { config, error } = useConfig();
  const { pathname } = useLocation();
  const inConferences = pathname === "/" || pathname.startsWith("/conferences/");

  return (
    <div className="flex h-dvh flex-col">
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-beige font-semibold text-navy focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:px-3 focus:py-2 focus:outline-navy"
      >
        Skip to content
      </a>
      {/* With page context (the Review page) the bar keeps every part down to laptop widths by tightening:
          below 1680px the product name stacks under the wordmark and the gaps narrow (more below 1366 and
          1280px, where the Review page's actions shrink too); below 1024px the
          context drops to a second row; on phones (<640px) only the mark stays in view. */}
      <header
        className={`on-navy flex min-h-16 shrink-0 items-center gap-y-1.5 bg-navy px-7 text-white ${context ? "gap-x-4 min-[1680px]:gap-x-6 max-[1366px]:gap-x-3.5 max-[1280px]:gap-x-3 max-lg:flex-wrap max-lg:px-4 max-lg:py-2.5" : "gap-x-6"}`}
      >
        <Link
          to="/"
          className={`flex shrink-0 items-center gap-3 rounded-sm ${context ? "max-[1680px]:border-r max-[1680px]:border-white/25 max-[1680px]:pr-4 max-sm:border-r-0 max-sm:pr-0" : ""}`}
        >
          <WoodlineMark className="h-[15px] w-10" />
          <span className={`flex items-center gap-5 ${context ? "max-[1680px]:flex-col max-[1680px]:items-start max-[1680px]:gap-0.5" : ""}`}>
            <span
              className={`font-wordmark text-[15px] uppercase leading-none tracking-[0.25em] ${context ? "max-[1680px]:text-[13px] max-sm:sr-only" : ""}`}
            >
              Woodline
            </span>
            <span
              className={`font-heading text-[15px] font-semibold text-white/85 ${context ? "min-[1680px]:border-l min-[1680px]:border-white/25 min-[1680px]:pl-5 max-[1680px]:text-xs max-[1680px]:leading-none max-sm:sr-only" : "border-l border-white/25 pl-5"}`}
            >
              Meeting Calendar Sync
            </span>
          </span>
        </Link>
        <div className={`flex min-w-0 flex-1 items-center gap-3 ${context ? "max-[1280px]:gap-2 max-lg:order-last max-lg:basis-full" : ""}`}>
          {context}
        </div>
        <nav
          aria-label="Main"
          className={`ml-auto flex shrink-0 items-center text-sm font-semibold ${context ? "gap-3.5 min-[1680px]:gap-5 max-[1366px]:gap-3 max-[1366px]:text-[13px]" : "gap-5"}`}
        >
          <NavLink to="/" end className={({ isActive }) => navClass(isActive || inConferences)}>
            Conferences
          </NavLink>
          <NavLink to="/roster" className={({ isActive }) => navClass(isActive)}>
            Roster
          </NavLink>
        </nav>
        {/* With page context in the bar the badges only fit on very wide screens; the Review page's sync
            status names the calendar route itself, so nothing is lost when they give way. */}
        <div className={`hidden shrink-0 items-center gap-2 ${context ? "min-[2200px]:flex" : "xl:flex"}`}>
          <ConfigBadges config={config} error={error} />
        </div>
        {actions && <div className="flex shrink-0 items-center gap-3 max-[1366px]:gap-2.5 max-[1280px]:gap-2 max-sm:min-w-0 max-sm:shrink max-sm:flex-wrap">{actions}</div>}
      </header>
      {config?.ephemeral && (
        <div
          role="note"
          className="flex shrink-0 items-center gap-2 border-b border-line bg-cream-2 px-7 py-1.5 text-[13px] font-medium text-ink"
        >
          <Info className="size-3.5 shrink-0 text-blue" aria-hidden="true" />
          Hosted demo — data resets when the server sleeps. Use sample schedules.
        </div>
      )}
      <main
        id="main"
        tabIndex={-1}
        className={`relative min-h-0 flex-1 focus:outline-none ${scroll ? "overflow-y-auto [scrollbar-gutter:stable]" : "overflow-hidden"}`}
      >
        {children}
      </main>
    </div>
  );
}
