// Typed thin wrapper over the backend HTTP API. Uses /api as the base so
// Vite's dev proxy forwards to the FastAPI server (see vite.config.ts).

import type {
  CreateRunResponse,
  DbOverview,
  DocSummary,
  DocText,
  GetRunResponse,
  RuleDetail,
  RuleSummary,
} from "./types";

const BASE = "/api";

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(`${path}: ${r.status} ${r.statusText}`);
  return (await r.json()) as T;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
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
  createRun: (doc_id: string, rule_ids?: string[]) =>
    postJson<CreateRunResponse>("/runs", { doc_id, rule_ids: rule_ids ?? null }),
  getRun: (run_id: string) => getJson<GetRunResponse>(`/runs/${run_id}`),
  streamUrl: (run_id: string) => `${BASE}/runs/${run_id}/stream`,
  dbOverview: () => getJson<DbOverview>("/admin/db/overview"),
};
