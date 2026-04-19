import { useEffect, useState } from "react";

import { api } from "../api";
import type { DbOverview } from "../types";

/** Read-only Postgres inspector — shows the three tables that make the
 * content-addressed caching story tangible:  runs, findings, router_calls.
 * Refreshes on click. Not a replacement for DataGrip, just a way to point at
 * persistence during the demo without Alt-Tabbing. */
export function AdminView() {
  const [data, setData] = useState<DbOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = () => {
    setLoading(true);
    setError(null);
    api.dbOverview().then(setData).catch((e) => setError(String(e))).finally(() => setLoading(false));
  };

  useEffect(load, []);

  return (
    <div className="flex-1 min-h-0 flex flex-col bg-slate-50 overflow-y-auto">
      <div className="px-6 py-3 border-b border-slate-200 bg-white flex items-center gap-4">
        <span className="text-sm text-slate-500">Postgres — last 20 rows per table</span>
        <button
          onClick={load}
          disabled={loading}
          className="ml-auto px-3 py-1 text-sm rounded border border-slate-300 bg-white hover:bg-slate-50 disabled:opacity-50"
        >
          {loading ? "…" : "Refresh"}
        </button>
      </div>

      {error && (
        <div className="px-6 py-3 bg-rose-50 text-rose-800 border-b border-rose-200 text-sm font-mono">
          {error}
        </div>
      )}

      {data && !data.connected && (
        <div className="px-6 py-3 bg-amber-50 text-amber-800 border-b border-amber-200 text-sm">
          Postgres not connected. Run <code className="font-mono">docker compose -f infra/docker-compose.yml up -d</code> to enable persistence.
        </div>
      )}

      {data && data.connected && (
        <div className="p-6 space-y-6">
          <Table title="runs" rows={data.runs} />
          <Table title="findings" rows={data.findings} />
          <Table title="router_calls" rows={data.router_calls} />
        </div>
      )}
    </div>
  );
}

function Table({ title, rows }: { title: string; rows: Record<string, unknown>[] }) {
  if (rows.length === 0) {
    return (
      <section>
        <h3 className="font-mono text-sm font-semibold text-slate-700 mb-2">{title}  <span className="text-slate-400 font-normal">(0 rows)</span></h3>
        <div className="text-sm text-slate-400 italic px-3 py-4 bg-white border border-slate-200 rounded">empty</div>
      </section>
    );
  }
  const cols = Object.keys(rows[0]);
  return (
    <section>
      <h3 className="font-mono text-sm font-semibold text-slate-700 mb-2">{title}  <span className="text-slate-400 font-normal">({rows.length} rows)</span></h3>
      <div className="overflow-x-auto bg-white border border-slate-200 rounded">
        <table className="min-w-full text-xs font-mono">
          <thead>
            <tr className="bg-slate-100 text-slate-600">
              {cols.map((c) => <th key={c} className="text-left px-3 py-2 border-b border-slate-200">{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="odd:bg-slate-50">
                {cols.map((c) => (
                  <td key={c} className="px-3 py-1.5 border-b border-slate-100 text-slate-700 whitespace-nowrap max-w-[24ch] truncate" title={String(row[c] ?? "")}>
                    {formatCell(row[c])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function formatCell(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "✓" : "✗";
  return String(v);
}
