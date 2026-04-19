import type { ExecutionGraph, RuleSummary, RunResult, RunStatus } from "../types";

interface Props {
  graph: ExecutionGraph;
  rules: RuleSummary[];
  result: RunResult | null;
  connectionState: string;
  traceId: string | null;
}

const STATUS_COLOR: Record<RunStatus, string> = {
  passed: "text-emerald-700 bg-emerald-50 border-emerald-300",
  failed: "text-rose-700 bg-rose-50 border-rose-300",
  degraded: "text-amber-700 bg-amber-50 border-amber-300",
};

const STATUS_LABEL: Record<RunStatus, string> = {
  passed: "Passed",
  failed: "Failed",
  degraded: "Degraded",
};

export function RunSummary({ graph, rules, result, connectionState, traceId }: Props) {
  const ruleIds = Object.keys(graph.roots);
  const ruleNames = Object.fromEntries(rules.map((r) => [r.id, r.name]));
  return (
    <aside className="border-l border-slate-200 bg-white p-6 w-80 flex flex-col gap-6 overflow-y-auto">
      <Section title="Run">
        {result ? (
          <div className="space-y-2">
            <div className={`inline-flex items-center px-3 py-1 rounded border font-semibold ${STATUS_COLOR[result.status]}`}>
              {STATUS_LABEL[result.status]}
            </div>
            <Row label="Run ID" value={<code className="text-sm">{result.run_id.slice(0, 8)}…</code>} />
            {traceId && (
              <Row
                label="Trace"
                value={
                  <a
                    href={`http://localhost:16686/trace/${traceId}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm text-sky-600 hover:text-sky-800 underline"
                  >
                    Open in Jaeger →
                  </a>
                }
              />
            )}
          </div>
        ) : (
          <div className="text-sm text-slate-500 italic">
            {connectionState === "open" ? "Streaming events…" : connectionState}
          </div>
        )}
      </Section>

      <Section title="Rule verdicts">
        <ul className="space-y-2">
          {ruleIds.map((rid) => {
            const name = ruleNames[rid] ?? rid;
            if (!result) {
              return (
                <li key={rid} className="flex flex-col gap-0.5 py-1.5 border-b border-slate-100 last:border-0">
                  <span className="text-sm text-slate-700">{name}</span>
                  <span className="text-xs text-slate-400 font-mono">{rid} · pending</span>
                </li>
              );
            }
            const passed = result.per_rule[rid];
            const errored = result.per_rule_errored[rid];
            const verdict = errored ? "Degraded" : passed ? "Pass" : "Fail";
            const cls = errored
              ? "text-amber-700 bg-amber-50 border-amber-300"
              : passed
                ? "text-emerald-700 bg-emerald-50 border-emerald-300"
                : "text-rose-700 bg-rose-50 border-rose-300";
            return (
              <li key={rid} className="flex justify-between items-center gap-3 py-1.5 border-b border-slate-100 last:border-0">
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-slate-800">{name}</div>
                  <div className="text-xs text-slate-400 font-mono">{rid}</div>
                </div>
                <span className={`shrink-0 px-2 py-0.5 text-xs font-semibold rounded border ${cls}`}>
                  {verdict}
                </span>
              </li>
            );
          })}
        </ul>
      </Section>

      <Section title="Graph">
        <div className="space-y-1">
          <Row label="Nodes" value={String(Object.keys(graph.nodes).length)} />
          <Row label="Leaves (LLM calls)" value={String(Object.values(graph.nodes).filter((n) => n.prompt_template).length)} />
          <Row label="Aggregators" value={String(Object.values(graph.nodes).filter((n) => !n.prompt_template).length)} />
        </div>
      </Section>
    </aside>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-3">{title}</h3>
      {children}
    </section>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between text-sm py-1">
      <span className="text-slate-600">{label}</span>
      <span className="font-medium text-slate-900">{value}</span>
    </div>
  );
}
