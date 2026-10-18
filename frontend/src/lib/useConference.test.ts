import { describe, expect, it } from "vitest";
import { ApiError, type ConferenceDetail } from "../api";
import { reduce, type State } from "./useConference";

const d1 = { id: 1, name: "A" } as ConferenceDetail;
const d2 = { id: 1, name: "B" } as ConferenceDetail;

describe("conference state", () => {
  it("loads, applies fresh detail, keeps old detail on error", () => {
    let s: State = { detail: null, error: null, loading: true };
    s = reduce(s, { type: "loaded", detail: d1 });
    expect(s).toEqual({ detail: d1, error: null, loading: false });
    s = reduce(s, { type: "failed", error: new ApiError(409, "Fix the problems", []) });
    expect(s.detail).toBe(d1);
    expect(s.error?.detail).toBe("Fix the problems");
    s = reduce(s, { type: "loaded", detail: d2 });
    expect(s).toEqual({ detail: d2, error: null, loading: false });
  });
});
