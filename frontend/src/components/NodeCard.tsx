import type { GraphNode, NodeFinding, NodeStatus } from "../types";

const STATUS_STYLES: Record<NodeStatus, string> = {
  pending:  "border-slate-300 bg-white text-slate-700",
  running:  "border-sky-500 bg-sky-50 text-sky-900 animate-pulse",
  passed:   "border-emerald-500 bg-emerald-50 text-emerald-900",
  failed:   "border-rose-500 bg-rose-50 text-rose-900",
  degraded: "border-amber-500 bg-amber-50 text-amber-900",
};

const STATUS_BADGE: Record<NodeStatus, string> = {
  pending:  "bg-slate-100 text-slate-600 border border-slate-300",
  running:  "bg-sky-100 text-sky-800 border border-sky-300",
  passed:   "bg-emerald-100 text-emerald-800 border border-emerald-300",
  failed:   "bg-rose-100 text-rose-800 border border-rose-300",
  degraded: "bg-amber-100 text-amber-800 border border-amber-300",
};

const STATUS_LABEL: Record<NodeStatus, string> = {
  pending: "Pending",
  running: "Running",
  passed: "Pass",
  failed: "Fail",
  degraded: "Degraded",
};

interface Props {
  node: GraphNode;
  status: NodeStatus;
  finding: NodeFinding | null;
  // False in the Rules view, where the DAG is shown for inspection only —
  // no status pill, neutral styling, no pass/fail colour semantics.
  showStatus?: boolean;
}

export function NodeCard({ node, status, finding, showStatus = true }: Props) {
  const isLeaf = node.prompt_template !== null;
  const param = Object.values(node.params)[0] ?? "";
  const cardClass = showStatus ? STATUS_STYLES[status] : STATUS_STYLES.pending;
  return (
    <div
      className={`rounded-lg border-2 p-3 shadow-sm ${cardClass}`}
      style={{ width: 280 }}
    >
      <div className="flex justify-between items-center mb-2 gap-2">
        <span className="font-semibold text-sm tracking-wide">{node.op}</span>
        {showStatus && (
          <span className={`text-[11px] font-semibold px-2 py-0.5 rounded ${STATUS_BADGE[status]}`}>
            {STATUS_LABEL[status]}
          </span>
        )}
      </div>
      <div className="font-mono text-[11px] text-slate-500 mb-2">{node.id.slice(0, 8)}</div>
      {isLeaf && param && (
        <div className="text-sm leading-snug italic text-slate-700 mb-1">
          “{truncate(param, 90)}”
        </div>
      )}
      {finding?.check_result?.evidence && (
        <div className="mt-2 pt-2 border-t border-current/20">
          <div className="text-[11px] uppercase tracking-wide text-slate-500 mb-1">
            Evidence{finding.check_result.page_ref !== null && ` · page ${finding.check_result.page_ref}`}
          </div>
          <div className="text-sm leading-snug">
            “{truncate(finding.check_result.evidence, 160)}”
          </div>
        </div>
      )}
    </div>
  );
}

function truncate(s: string, max: number): string {
  return s.length <= max ? s : s.slice(0, max - 1) + "…";
}
