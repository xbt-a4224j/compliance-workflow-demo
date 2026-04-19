import { useState } from "react";

interface Props {
  onSave: (token: string) => void;
  error?: string;
}

/** Blocking modal shown at startup and whenever the API rejects our token.
 * Token goes to localStorage — no cookies, no login session. Matches the
 * backend's "one shared bearer token in .env" model (see api/auth.py). */
export function TokenPrompt({ onSave, error }: Props) {
  const [value, setValue] = useState("");
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = value.trim();
    if (trimmed) onSave(trimmed);
  };
  return (
    <div className="h-full flex items-center justify-center bg-slate-50">
      <form
        onSubmit={submit}
        className="w-full max-w-md bg-white border border-slate-200 rounded-lg shadow-sm p-6 space-y-4"
      >
        <div>
          <h1 className="text-lg font-semibold text-slate-900">API token</h1>
          <p className="text-sm text-slate-500 mt-1">
            This demo's API requires a bearer token. Paste the{" "}
            <code className="font-mono text-slate-700">AUTH_TOKEN</code> from{" "}
            <code className="font-mono text-slate-700">.env</code>. It's saved
            locally and sent on every API call.
          </p>
        </div>
        <input
          type="password"
          autoFocus
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="token"
          className="w-full px-3 py-2 rounded border border-slate-300 font-mono text-sm
                     focus:outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
        />
        {error && (
          <div className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded px-3 py-2">
            {error}
          </div>
        )}
        <button
          type="submit"
          disabled={!value.trim()}
          className="w-full px-4 py-2 rounded font-medium bg-sky-600 text-white
                     hover:bg-sky-700 disabled:bg-slate-200 disabled:text-slate-400
                     disabled:cursor-not-allowed transition-colors"
        >
          Connect
        </button>
      </form>
    </div>
  );
}
