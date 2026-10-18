import { useEffect, useState } from "react";
import { ApiError, getConfig, type AppConfig } from "../api";

// /api/config is read once per page load and shared, so the shell badges don't flicker on navigation.
let pending: Promise<AppConfig> | null = null;
let resolved: AppConfig | null = null;

export function loadConfig(force = false): Promise<AppConfig> {
  if (force || !pending) {
    pending = getConfig().then(
      (config) => (resolved = config),
      (error) => {
        pending = null;
        throw error;
      },
    );
  }
  return pending;
}

export interface ConfigState {
  config: AppConfig | null;
  error: string | null;
}

export function useConfig(): ConfigState {
  const [state, setState] = useState<ConfigState>({ config: resolved, error: null });
  useEffect(() => {
    let live = true;
    loadConfig().then(
      (config) => live && setState({ config, error: null }),
      (error) => live && setState({ config: null, error: error instanceof ApiError ? error.detail : String(error) }),
    );
    return () => {
      live = false;
    };
  }, []);
  return state;
}
