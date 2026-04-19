import { useEffect, useState } from "react";

import {
  AUTH_EXPIRED_EVENT,
  api,
  getAuthToken,
  setAuthToken,
} from "./api";
import { AdminView } from "./components/AdminView";
import { DagView } from "./components/DagView";
import { DocumentPane } from "./components/DocumentPane";
import { RuleEditor } from "./components/RuleEditor";
import { RunSelector } from "./components/RunSelector";
import { RunSummary } from "./components/RunSummary";
import { TokenPrompt } from "./components/TokenPrompt";
import { useRunStream } from "./hooks/useRunStream";
import type { CreateRunResponse, DocSummary, RuleSummary } from "./types";

type View = "run" | "rules" | "admin";

export default function App() {
  const [token, setToken] = useState<string | null>(() => getAuthToken());
  const [authError, setAuthError] = useState<string | null>(null);
  const [view, setView] = useState<View>("run");
  const [rules, setRules] = useState<RuleSummary[]>([]);
  const [docs, setDocs] = useState<DocSummary[]>([]);
  const [docId, setDocId] = useState("");
  const [run, setRun] = useState<CreateRunResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // The API layer fires this event when any response comes back 401 — the
  // stored token has been cleared, re-prompt the user.
  useEffect(() => {
    const onExpired = () => {
      setToken(null);
      setAuthError("Token rejected. Check AUTH_TOKEN in .env and try again.");
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
  }, []);

  const handleTokenSave = (t: string) => {
    setAuthToken(t);
    setToken(t);
    setAuthError(null);
  };

  // Block the whole app until we have a token — no partial render with
  // half-populated state. Matches the backend's "auth required, no escape
  // hatch" contract.
  if (!token) {
    return <TokenPrompt onSave={handleTokenSave} error={authError ?? undefined} />;
  }

  // Bootstrap: load rules + docs once. Rules feed the swimlane labels.
  useEffect(() => {
    Promise.all([api.listRules(), api.listDocs()])
      .then(([r, d]) => {
        setRules(r);
        setDocs(d);
      })
      .catch((e) => setError(String(e)));
  }, []);

  const stream = useRunStream(run?.run_id ?? null, run?.dag ?? null);

  const handleRun = async () => {
    setBusy(true);
    setError(null);
    try {
      // Omitting rule_ids → backend evaluates every loaded rule in one DAG.
      const result = await api.createRun(docId);
      setRun(result);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="h-full flex flex-col">
      <header className="px-6 py-3 border-b border-slate-200 bg-white flex items-baseline gap-4 shadow-sm">
        <h1 className="text-lg font-semibold tracking-tight text-slate-900">compliance-workflow-demo</h1>
        <span className="text-sm text-slate-500">
          Compliance rule checker · live DAG visualization
        </span>
        <nav className="ml-auto flex gap-1">
          <ViewTab active={view === "run"} onClick={() => setView("run")}>Run</ViewTab>
          <ViewTab active={view === "rules"} onClick={() => setView("rules")}>Rules</ViewTab>
          <ViewTab active={view === "admin"} onClick={() => setView("admin")}>Admin</ViewTab>
        </nav>
      </header>

      {view === "run" && (
        <RunSelector
          docs={docs}
          docId={docId}
          busy={busy || (!!run && stream.connectionState !== "closed" && !stream.result)}
          onDocChange={setDocId}
          onRun={handleRun}
        />
      )}

      {error && (
        <div className="px-6 py-3 bg-rose-50 text-rose-800 border-b border-rose-200 text-sm font-mono">
          {error}
        </div>
      )}

      {view === "run" ? (
        <div className="flex-1 flex min-h-0">
          <main className="flex-1 min-w-0 flex flex-col bg-slate-50">
            {run ? (
              <>
                <div className="flex-1 min-h-0">
                  <DagView
                    graph={run.dag}
                    rules={rules}
                    statuses={stream.statuses}
                    findings={stream.findings}
                    result={stream.result}
                  />
                </div>
                <div className="h-72 min-h-[18rem] max-h-[40vh] resize-y overflow-hidden">
                  <DocumentPane docId={docId} findings={stream.findings} />
                </div>
              </>
            ) : (
              <Placeholder />
            )}
          </main>
          {run && (
            <RunSummary
              graph={run.dag}
              rules={rules}
              result={stream.result}
              connectionState={stream.connectionState}
              traceId={run.trace_id}
            />
          )}
        </div>
      ) : view === "rules" ? (
        <RuleEditor rules={rules} />
      ) : (
        <AdminView />
      )}
    </div>
  );
}

function ViewTab({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
        active
          ? "bg-slate-900 text-white"
          : "text-slate-600 hover:bg-slate-100"
      }`}
    >
      {children}
    </button>
  );
}

function Placeholder() {
  return (
    <div className="h-full flex items-center justify-center px-8">
      <div className="max-w-md text-center text-slate-500 text-base">
        Pick a document, then click <strong className="text-slate-700">Check all rules</strong>.
        Each rule appears as its own lane; nodes light up live as the engine
        evaluates them.
      </div>
    </div>
  );
}
