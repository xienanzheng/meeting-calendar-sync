// Typed client for the FastAPI backend. Types mirror backend/mcs/schemas.py field for field (snake_case kept).

export type SyncState = "not_sent" | "sent" | "changed" | "failed" | "cancelled";
export type ReviewState = "needs_attention" | "ready" | "verified" | "sent" | "cancelled";
export type MeetingFormat = "one_on_one" | "group" | "meal" | "other";
export type MeetingStatus = "draft" | "confirmed" | "cancelled";
export type Severity = "block" | "warn";

export interface Flag {
  code: string;
  severity: Severity;
  message: string;
}

export interface Attendee {
  analyst_id: number;
  name: string;
  email: string;
  match: string; // exact | alias | initial | fuzzy | manual | default | removed
  sync: SyncState;
  sync_error: string | null;
}

export interface Meeting {
  id: number;
  conference_id: number;
  date: string | null; // YYYY-MM-DD
  start: string | null; // HH:MM, hotel-local
  end: string | null;
  end_assumed: boolean;
  timezone: string | null; // the meeting's own zone; null follows the conference's
  room: string;
  company: string;
  ticker: string | null;
  format: MeetingFormat;
  company_attendees: string[];
  raw_attendee_names: string[];
  ignored_names: string[];
  unmatched_names: string[];
  notes: string;
  source_page: number | null;
  status: MeetingStatus;
  review_state: ReviewState;
  attendees: Attendee[];
  removed: Attendee[]; // colleagues taken off a sent meeting; removed from their calendar on next send
  flags: Flag[];
}

export interface Counts {
  total: number;
  needs_attention: number;
  ready: number;
  verified: number;
  sent: number;
  cancelled: number;
  warnings: number;
  changed: number;
  failed: number;
  pending_actions: number;
}

export interface ConferenceSummary {
  id: number;
  name: string;
  broker: string;
  hotel: string;
  city: string;
  timezone: string | null;
  created_at: string;
  first_date: string | null;
  last_date: string | null;
  counts: Counts;
}

/** What the server's same-request calendar sync did after a change (spec §15.1). */
export interface SyncSummary {
  ok: number;
  failed: number;
  message: string;
}

export type FieldValue = string | string[] | null;

export interface FieldChange {
  field: string; // date | start | end | room | format | ticker | company | company_attendees | firm_attendees
  before: FieldValue;
  after: FieldValue;
}

/** A meeting row as the broker's revised PDF prints it. */
export interface ProposedMeeting {
  date: string | null;
  start: string | null;
  end: string | null;
  room: string | null;
  company: string;
  ticker: string | null;
  format: MeetingFormat;
  firm_attendees: string[];
  company_attendees: string[];
  page: number | null;
}

export type RevisionChangeKind = "changed" | "added" | "removed";

export interface RevisionChange {
  id: string;
  kind: RevisionChangeKind;
  meeting_id: number | null;
  company: string;
  summary: string;
  fields: FieldChange[];
  new: ProposedMeeting | null;
}

export interface Revision {
  id: number;
  number: number;
  pdf_filename: string;
  created_at: string;
  changes: RevisionChange[];
  unchanged_count: number;
}

export interface ConferenceDetail extends ConferenceSummary {
  schedule_for: string;
  pdf_filename: string;
  extractor: string;
  meetings: Meeting[];
  skipped_items: number;
  last_sync: SyncSummary | null;
  pending_revision: Revision | null;
  revision_number: number;
}

export interface Analyst {
  id: number;
  name: string;
  email: string;
  aliases: string[];
  active: boolean;
}

export interface AnalystIn {
  name: string;
  email: string;
  aliases?: string[];
  active?: boolean;
}

export type AnalystUpdate = Partial<AnalystIn>;

export interface MeetingCreate {
  company: string;
  date?: string | null;
  start?: string | null;
  end?: string | null;
  room?: string;
  ticker?: string | null;
  format?: MeetingFormat;
  attendee_ids?: number[];
  notes?: string;
}

export interface MeetingUpdate {
  date?: string | null;
  start?: string | null;
  end?: string | null;
  timezone?: string | null; // null: follow the conference
  room?: string;
  company?: string;
  ticker?: string | null;
  format?: MeetingFormat;
  company_attendees?: string[];
  notes?: string;
  attendee_ids?: number[];
  ignored_names?: string[];
}

export interface ConferenceUpdate {
  name?: string;
  broker?: string;
  hotel?: string;
  city?: string;
  timezone?: string | null;
}

export interface SendAction {
  kind: "create" | "update" | "cancel";
  meeting_id: number;
  analyst_id: number;
  analyst_name: string;
  subject: string | null;
  ok: boolean | null;
  error: string | null;
}

export interface AnalystSendSummary {
  analyst_id: number;
  name: string;
  create: number;
  update: number;
  cancel: number;
  failed: number;
  download_url: string | null;
}

export interface SendResult {
  sink: string;
  dry_run: boolean;
  actions: SendAction[];
  by_analyst: AnalystSendSummary[];
  ok_count: number;
  failed_count: number;
  zip_url: string | null;
}

export interface GraphStatus {
  configured: boolean;
  signed_in: boolean;
  pending: boolean;
  account: string | null;
  error: string | null;
}

export interface GraphLoginStart {
  user_code: string;
  verification_uri: string;
  message: string;
  expires_in: number | null;
}

export interface AppConfig {
  extractor: string; // anthropic | claude-code | foundry | fake
  model: string;
  calendar_sink: "ics" | "graph" | "outlook-demo" | "google-demo";
  calendar_target?: { account: string; name: string } | null;
  ephemeral: boolean;
  graph: GraphStatus;
}

export class ApiError extends Error {
  status: number;
  detail: string;
  flags: Flag[];

  constructor(status: number, detail: string, flags: Flag[] = []) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.flags = flags;
  }
}

/** The human-readable message for anything a request can throw. */
export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Something went wrong. Try again.";
}

// FastAPI validation errors (422) carry a list of {loc, msg}; everything else carries a string.
function detailText(detail: unknown, status: number): string {
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail)) {
    const msgs = detail.map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : "")).filter(Boolean);
    if (msgs.length) return msgs.join("; ");
  }
  return `Request failed (${status})`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: init.body instanceof FormData ? init.headers : { "Content-Type": "application/json", ...init.headers },
    });
  } catch {
    throw new ApiError(0, "Can't reach the Meeting Calendar Sync server. Check that it is running, then try again.");
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, detailText(body.detail, res.status), body.flags ?? []);
  return body as T;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
});

// ---------- system ----------
export const getConfig = () => request<AppConfig>("/api/config");
export const graphLogin = () => request<GraphLoginStart>("/api/graph/login", { method: "POST" });
export const graphStatus = () => request<GraphStatus>("/api/graph/status");

// ---------- conferences ----------
export const listConferences = () => request<ConferenceSummary[]>("/api/conferences");
export const getConference = (id: number) => request<ConferenceDetail>(`/api/conferences/${id}`);
/** `mode` "auto" (the server default) treats a matching upload as a revision; "new" always makes a new conference. */
export const uploadConference = (file: File, defaultIds: number[], mode?: "auto" | "new") => {
  const form = new FormData();
  form.append("file", file);
  form.append("default_attendee_ids", defaultIds.join(","));
  if (mode) form.append("mode", mode);
  return request<ConferenceDetail>("/api/conferences", { method: "POST", body: form });
};
export const patchConference = (id: number, body: ConferenceUpdate) =>
  request<ConferenceDetail>(`/api/conferences/${id}`, json("PATCH", body));
export const deleteConference = (id: number) => request<void>(`/api/conferences/${id}`, { method: "DELETE" });
/**
 * The conference's source PDF. Applying a revision swaps the file behind the same path, so pass the
 * conference's `revision_number` as `version`: the URL changes with it and the frame reloads.
 */
export const pdfUrl = (cid: number, page?: number | null, version?: number) =>
  `/api/conferences/${cid}/pdf${version ? `?rev=${version}` : ""}${page ? `#page=${page}` : ""}`;
export const icsUrl = (cid: number, analystId: number) => `/api/conferences/${cid}/ics/${analystId}`;
export const icsZipUrl = (cid: number) => `/api/conferences/${cid}/ics.zip`;

// ---------- broker revisions ----------
export const uploadRevision = (cid: number, file: File) => {
  const form = new FormData();
  form.append("file", file);
  return request<ConferenceDetail>(`/api/conferences/${cid}/revisions`, { method: "POST", body: form });
};
/** Applies the accepted change ids; null applies every change. Calendars sync in the same request. */
export const applyRevision = (rid: number, accepted: string[] | null) =>
  request<ConferenceDetail>(`/api/revisions/${rid}/apply`, json("POST", { accepted }));
export const discardRevision = (rid: number) => request<ConferenceDetail>(`/api/revisions/${rid}/discard`, { method: "POST" });
export const revisionAsNewConference = (rid: number) =>
  request<ConferenceDetail>(`/api/revisions/${rid}/as-new-conference`, { method: "POST" });
export const revisionPdfUrl = (rid: number, page?: number | null) => `/api/revisions/${rid}/pdf${page ? `#page=${page}` : ""}`;

// ---------- meetings ----------
export const addMeeting = (cid: number, body: MeetingCreate) =>
  request<ConferenceDetail>(`/api/conferences/${cid}/meetings`, json("POST", body));
export const patchMeeting = (id: number, body: MeetingUpdate) =>
  request<ConferenceDetail>(`/api/meetings/${id}`, json("PATCH", body));
export const confirmMeeting = (id: number) => request<ConferenceDetail>(`/api/meetings/${id}/confirm`, { method: "POST" });
export const unconfirmMeeting = (id: number) =>
  request<ConferenceDetail>(`/api/meetings/${id}/unconfirm`, { method: "POST" });
export const deleteMeeting = (id: number) => request<ConferenceDetail>(`/api/meetings/${id}`, { method: "DELETE" });
export const confirmReady = (cid: number, meetingIds?: number[]) =>
  request<ConferenceDetail>(`/api/conferences/${cid}/confirm-ready`, json("POST", { meeting_ids: meetingIds ?? null }));

// ---------- send ----------
export const sendPreview = (cid: number) => request<SendResult>(`/api/conferences/${cid}/send?dry_run=true`, { method: "POST" });
export const sendNow = (cid: number) => request<SendResult>(`/api/conferences/${cid}/send?dry_run=false`, { method: "POST" });
/** Verifying syncs calendars on its own; this is the Retry path after a failed sync. */
export const retrySync = (cid: number) => sendNow(cid);

// ---------- roster ----------
export const listRoster = () => request<Analyst[]>("/api/roster");
export const createAnalyst = (body: AnalystIn) => request<Analyst>("/api/roster", json("POST", body));
export const updateAnalyst = (id: number, body: AnalystUpdate) => request<Analyst>(`/api/roster/${id}`, json("PATCH", body));
export const deleteAnalyst = (id: number) => request<void>(`/api/roster/${id}`, { method: "DELETE" });
