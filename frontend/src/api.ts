// Typed thin wrapper over the backend HTTP API. Uses /api as the base so
// Vite's dev proxy forwards to the FastAPI server (see vite.config.ts).

import type {
  CreateRunResponse,
  DbOverview,
  DocSummary,
  DocText,
  GetRunResponse,
  LogLevel,
  LogsResponse,
  RuleDetail,
  RuleSummary,
} from "./types";

const BASE = "/api";
const TOKEN_KEY = "authToken";

export const getAuthToken = (): string | null => localStorage.getItem(TOKEN_KEY);
export const setAuthToken = (t: string): void => localStorage.setItem(TOKEN_KEY, t);
export const clearAuthToken = (): void => localStorage.removeItem(TOKEN_KEY);

/** App-wide event fired when the server rejects the stored token — top-level
 * component listens and re-shows the token prompt. */
export const AUTH_EXPIRED_EVENT = "auth-expired";

function authHeaders(): Record<string, string> {
  const t = getAuthToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

function handle401(status: number) {
  if (status === 401) {
    clearAuthToken();
    window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
  }
}

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { headers: authHeaders() });
  handle401(r.status);
  if (!r.ok) throw new Error(`${path}: ${r.status} ${r.statusText}`);
  return (await r.json()) as T;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  handle401(r.status);
  if (!r.ok) {
    const detail = await r.text();
    throw new Error(`${path}: ${r.status} ${r.statusText}\n${detail}`);
  }
  return (await r.json()) as T;
}

async function deleteJson<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { method: "DELETE", headers: authHeaders() });
  handle401(r.status);
  if (!r.ok) {
    const detail = await r.text();
    throw new Error(`${path}: ${r.status} ${r.statusText}\n${detail}`);
  }
  return (await r.json()) as T;
}

export const api = {
  listRules: () => getJson<RuleSummary[]>("/rules"),
  getRule: (rule_id: string) => getJson<RuleDetail>(`/rules/${rule_id}`),
  listDocs: () => getJson<DocSummary[]>("/docs"),
  getDocText: (doc_id: string) => getJson<DocText>(`/docs/${doc_id}/text`),
  createRun: (doc_id: string, opts: { rule_ids?: string[]; skip_cache?: boolean } = {}) =>
    postJson<CreateRunResponse>("/runs", {
      doc_id,
      rule_ids: opts.rule_ids ?? null,
      skip_cache: opts.skip_cache ?? false,
    }),
  getRun: (run_id: string) => getJson<GetRunResponse>(`/runs/${run_id}`),
  streamUrl: (run_id: string) => {
    // EventSource can't send custom headers, so the token rides as a query
    // param (accepted by require_token as a fallback to the Bearer header).
    const t = getAuthToken();
    return t
      ? `${BASE}/runs/${run_id}/stream?token=${encodeURIComponent(t)}`
      : `${BASE}/runs/${run_id}/stream`;
  },
  dbOverview: () => getJson<DbOverview>("/admin/db/overview"),
  logs: (minLevel: LogLevel = "INFO", limit = 200) =>
    getJson<LogsResponse>(`/admin/logs?min_level=${minLevel}&limit=${limit}`),
  resetData: () =>
    deleteJson<{ runs: number; findings: number; router_calls: number }>("/admin/data"),
};
