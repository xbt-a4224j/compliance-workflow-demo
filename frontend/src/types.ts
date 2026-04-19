// Mirrors backend pydantic models in src/compliance_workflow_demo/api/schemas.py and
// src/compliance_workflow_demo/executor/run.py. Kept by hand for v1 — small surface area.

export type NodeOp = "ALL_OF" | "ANY_OF" | "REQUIRES_CLAUSE" | "FORBIDS_PHRASE" | "CITES";

export interface GraphNode {
  id: string;
  op: NodeOp;
  params: Record<string, string>;
  child_ids: string[];
  prompt_template: string | null;
}

export interface ExecutionGraph {
  nodes: Record<string, GraphNode>;
  topo_order: string[];
  roots: Record<string, string>; // rule_id → node_id
}

export interface RuleSummary {
  id: string;
  name: string;
  op: NodeOp;
}

export interface DocSummary {
  id: string;        // filename stem (e.g. "synth_fund_01")
  title: string;     // human-friendly name from the doc's first line
  sha256: string;
  pages: number;
}

export interface DocPage {
  page: number;
  text: string;
}

export interface DocText {
  id: string;
  title: string;
  sha256: string;
  pages: DocPage[];
}

export interface CheckResult {
  check_id: string;
  passed: boolean;
  evidence: string | null;
  page_ref: number | null;
  confidence: number;
}

export interface NodeFinding {
  node_id: string;
  op: string;
  passed: boolean;
  errored: boolean;
  check_result: CheckResult | null;
  children_passed: boolean[] | null;
}

export type RunStatus = "passed" | "failed" | "degraded";

export interface RunResult {
  run_id: string;
  status: RunStatus;
  per_rule: Record<string, boolean>;
  per_rule_errored: Record<string, boolean>;
  findings: Record<string, NodeFinding>;
  errors: Record<string, string>;
}

export interface CreateRunResponse {
  run_id: string;
  dag: ExecutionGraph;
}

export interface GetRunResponse {
  run_id: string;
  rule_id: string;
  doc_id: string;
  dag: ExecutionGraph;
  result: RunResult | null;
}

// SSE events from /runs/:id/stream
export type EventKind = "run_started" | "check_started" | "check_finished" | "run_finished";

export interface OrchestratorEvent {
  kind: EventKind;
  run_id: string;
  node_id: string | null;
  finding: NodeFinding | null;
  result: RunResult | null;
}

// UI-only enrichment: per-node lifecycle status
export type NodeStatus = "pending" | "running" | "passed" | "failed" | "degraded";
