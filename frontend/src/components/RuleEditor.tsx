import { useEffect, useState } from "react";

import { api } from "../api";
import type { RuleDetail, RuleSummary } from "../types";
import { DagView } from "./DagView";

interface Props {
  rules: RuleSummary[];
}

/** Rules view: list on the left, authored YAML middle, compiled DAG on the
 * right. Read-only inspection pane — no editing/save plumbing yet. */
export function RuleEditor({ rules }: Props) {
  const [selectedId, setSelectedId] = useState<string>(rules[0]?.id ?? "");
  const [detail, setDetail] = useState<RuleDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedId) return;
    setDetail(null);
    setError(null);
    api.getRule(selectedId).then(setDetail).catch((e) => setError(String(e)));
  }, [selectedId]);

  return (
    <div className="flex-1 flex min-h-0 bg-slate-50">
      {/* Rule list */}
      <aside className="w-64 shrink-0 border-r border-slate-200 bg-white overflow-y-auto">
        <ul className="divide-y divide-slate-100">
          {rules.map((r) => (
            <li key={r.id}>
              <button
                onClick={() => setSelectedId(r.id)}
                className={`w-full text-left px-4 py-3 hover:bg-slate-50 transition-colors ${
                  r.id === selectedId ? "bg-sky-50 border-l-2 border-sky-500" : ""
                }`}
              >
                <div className="text-sm font-medium text-slate-800">{r.name}</div>
                <div className="text-xs text-slate-400 font-mono mt-0.5">{r.id} · {r.op}</div>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      {/* YAML + DAG */}
      <div className="flex-1 min-w-0 flex flex-col">
        {error && (
          <div className="px-6 py-3 bg-rose-50 text-rose-800 border-b border-rose-200 text-sm font-mono">
            {error}
          </div>
        )}
        {detail ? (
          <>
            <div className="px-6 py-3 bg-white border-b border-slate-200">
              <div className="text-sm text-slate-500">Rule</div>
              <div className="text-base font-semibold text-slate-900">{detail.name}</div>
            </div>

            <div className="flex-1 flex min-h-0">
              {/* YAML pane */}
              <div className="w-1/2 min-w-0 border-r border-slate-200 flex flex-col">
                <div className="px-4 py-2 text-xs uppercase tracking-wider text-slate-500 bg-slate-100 border-b border-slate-200">
                  Authored YAML  <span className="text-slate-400 normal-case tracking-normal">— human-editable policy</span>
                </div>
                <textarea
                  readOnly
                  value={detail.yaml_source}
                  className="flex-1 p-4 font-mono text-sm bg-white text-slate-800 resize-none focus:outline-none"
                />
              </div>

              {/* DAG pane */}
              <div className="w-1/2 min-w-0 flex flex-col">
                <div className="px-4 py-2 text-xs uppercase tracking-wider text-slate-500 bg-slate-100 border-b border-slate-200">
                  Compiled DAG  <span className="text-slate-400 normal-case tracking-normal">— one leaf = one LLM call</span>
                </div>
                <div className="flex-1 min-h-0">
                  <DagView
                    graph={detail.dag}
                    rules={[{ id: detail.id, name: detail.name, op: detail.op }]}
                    statuses={{}}
                    findings={{}}
                    result={null}
                  />
                </div>
              </div>
            </div>
          </>
        ) : !error ? (
          <div className="flex-1 flex items-center justify-center text-slate-400">
            loading rule…
          </div>
        ) : null}
      </div>
    </div>
  );
}
