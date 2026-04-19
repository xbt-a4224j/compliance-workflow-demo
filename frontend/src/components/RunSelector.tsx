import type { DocSummary } from "../types";

interface Props {
  docs: DocSummary[];
  docId: string;
  busy: boolean;
  skipCache: boolean;
  onDocChange: (id: string) => void;
  onSkipCacheChange: (v: boolean) => void;
  onRun: () => void;
}

export function RunSelector({
  docs, docId, busy, skipCache, onDocChange, onSkipCacheChange, onRun,
}: Props) {
  const canRun = !!docId && !busy;
  return (
    <div className="flex flex-wrap items-end gap-4 px-6 py-4 border-b border-slate-200 bg-white">
      <Field label="Document">
        <select
          value={docId}
          onChange={(e) => onDocChange(e.target.value)}
          style={{ minWidth: 380 }}
          className="px-3 py-2 rounded bg-white border border-slate-300 text-base
                     hover:border-slate-400
                     focus:outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
        >
          <option value="">— select a document —</option>
          {docs.map((d) => (
            <option key={d.id} value={d.id}>
              {d.title}
              {d.id.startsWith("real_") ? "  ★ authentic SEC filing" : ""}
            </option>
          ))}
        </select>
      </Field>

      <label
        className="flex items-center gap-2 pb-2 text-sm text-slate-600 cursor-pointer select-none"
        title="Bypass the findings cache so every leaf re-calls the LLM (slower; shows real cost)"
      >
        <input
          type="checkbox"
          checked={skipCache}
          onChange={(e) => onSkipCacheChange(e.target.checked)}
          className="h-4 w-4 accent-sky-600"
        />
        Skip cache
      </label>

      <button
        onClick={onRun}
        disabled={!canRun}
        className="ml-auto px-5 py-2 rounded font-medium text-base
                   bg-sky-600 text-white hover:bg-sky-700 active:bg-sky-800
                   disabled:bg-slate-200 disabled:text-slate-400 disabled:cursor-not-allowed
                   shadow-sm transition-colors"
      >
        {busy ? "Checking…" : "Check all rules"}
      </button>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-sm font-medium text-slate-600">{label}</span>
      {children}
    </label>
  );
}
