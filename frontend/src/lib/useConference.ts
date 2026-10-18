import { useCallback, useEffect, useReducer, useRef } from "react";
import { ApiError, errorMessage, getConference, type ConferenceDetail } from "../api";

export interface State {
  detail: ConferenceDetail | null;
  /** The latest load or mutation failure; cleared by the next fresh detail. */
  error: ApiError | null;
  loading: boolean;
}

export type Action =
  | { type: "loading" }
  | { type: "loaded"; detail: ConferenceDetail }
  | { type: "failed"; error: ApiError };

/** Every mutation answers with the whole conference, so the page only ever swaps in fresh detail. */
export function reduce(state: State, action: Action): State {
  switch (action.type) {
    case "loading":
      return { detail: null, error: null, loading: true };
    case "loaded":
      return { detail: action.detail, error: null, loading: false };
    case "failed":
      // A failed edit keeps what's on screen; only the error is new.
      return { ...state, error: action.error, loading: false };
  }
}

const toApiError = (error: unknown) => (error instanceof ApiError ? error : new ApiError(0, errorMessage(error)));

/**
 * Loads conference `id` and applies the detail every mutation returns. `apply` resolves with the
 * fresh detail, or records the failure and rethrows it as an ApiError so the control that acted
 * can show it in place. A response that arrives after a newer one is ignored.
 */
export function useConference(id: number) {
  const [state, dispatch] = useReducer(reduce, { detail: null, error: null, loading: true });
  const currentId = useRef(id);
  const issued = useRef(0);
  const shown = useRef(0);

  const apply = useCallback(async (promise: Promise<ConferenceDetail>): Promise<ConferenceDetail> => {
    const ticket = ++issued.current;
    const forId = currentId.current;
    try {
      const detail = await promise;
      if (forId === currentId.current && ticket >= shown.current) {
        shown.current = ticket;
        dispatch({ type: "loaded", detail });
      }
      return detail;
    } catch (error) {
      const failure = toApiError(error);
      if (forId === currentId.current) dispatch({ type: "failed", error: failure });
      throw failure;
    }
  }, []);

  const reload = useCallback(() => apply(getConference(currentId.current)), [apply]);

  useEffect(() => {
    currentId.current = id;
    dispatch({ type: "loading" });
    apply(getConference(id)).catch(() => undefined); // the failure is in state.error
  }, [id, apply]);

  return { ...state, apply, reload };
}
