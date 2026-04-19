import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import type { LogEntry, LogLevel } from "../types";

const LEVELS: LogLevel[] = ["INFO", "WARNING", "ERROR"];

const LEVEL_BADGE: Record<LogLevel, string> = {
  DEBUG: "bg-slate-100 text-slate-600",
  INFO: "bg-sky-100 text-sky-800",
  WARNING: "bg-amber-100 text-amber-800",
  ERROR: "bg-rose-100 text-rose-800",
  CRITICAL: "bg-rose-200 text-rose-900",
};

/** Read-only view onto the backend's in-memory log buffer. Polls every 3s
 * unless paused. Newest entries first. */
export function LogsView() {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [minLevel, setMinLevel] = useState<LogLevel>("INFO");
  const [paused, setPaused] = useState(false);
  const minLevelRef = useRef(minLevel);
  minLevelRef.current = minLevel;

  const load = () => {
    api
      .logs(minLevelRef.current, 200)
      .then((r) => {
        setEntries(r.entries);
        setError(null);
      })
      .catch((e) => setError(String(e)));
  };

  useEffect(() => {
    load();
  }, [minLevel]);

  useEffect(() => {
    if (paused) return;
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, [paused]);

  return (
    <div className="flex-1 min-h-0 flex flex-col bg-slate-50">
      <div className="px-6 py-3 border-b border-slate-200 bg-white flex items-center gap-3">
        <span className="text-sm text-slate-500">
          Backend logs · in-memory ring buffer · newest first
        </span>
        <div className="ml-auto flex items-center gap-2">
          <label className="text-xs text-slate-500">level:</label>
          <select
            value={minLevel}
            onChange={(e) => setMinLevel(e.target.value as LogLevel)}
            className="text-sm border border-slate-300 rounded px-2 py-1 bg-white"
          >
            {LEVELS.map((l) => (
              <option key={l} value={l}>{l}+</option>
            ))}
          </select>
          <button
            onClick={() => setPaused((p) => !p)}
            className="px-3 py-1 text-sm rounded border border-slate-300 bg-white hover:bg-slate-50"
            title={paused ? "Resume auto-refresh" : "Pause auto-refresh (3s)"}
          >
            {paused ? "Resume" : "Pause"}
          </button>
          <button
            onClick={load}
            className="px-3 py-1 text-sm rounded border border-slate-300 bg-white hover:bg-slate-50"
          >
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="px-6 py-3 bg-rose-50 text-rose-800 border-b border-rose-200 text-sm font-mono">
          {error}
        </div>
      )}

      <div className="flex-1 min-h-0 overflow-y-auto">
        {entries.length === 0 ? (
          <div className="h-full flex items-center justify-center text-slate-400 text-sm">
            no entries at {minLevel}+
          </div>
        ) : (
          <table className="min-w-full text-xs font-mono">
            <thead className="sticky top-0 bg-slate-100 text-slate-600">
              <tr>
                <th className="text-left px-3 py-2 border-b border-slate-200 w-44">timestamp</th>
                <th className="text-left px-3 py-2 border-b border-slate-200 w-20">level</th>
                <th className="text-left px-3 py-2 border-b border-slate-200 w-64">logger</th>
                <th className="text-left px-3 py-2 border-b border-slate-200">message</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id} className="odd:bg-white even:bg-slate-50">
                  <td className="px-3 py-1.5 border-b border-slate-100 text-slate-500 whitespace-nowrap">
                    {e.ts}
                  </td>
                  <td className="px-3 py-1.5 border-b border-slate-100">
                    <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${LEVEL_BADGE[e.level]}`}>
                      {e.level}
                    </span>
                  </td>
                  <td className="px-3 py-1.5 border-b border-slate-100 text-slate-600 whitespace-nowrap">
                    {e.logger}
                  </td>
                  <td className="px-3 py-1.5 border-b border-slate-100 text-slate-800 whitespace-pre-wrap break-words">
                    {e.message}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
