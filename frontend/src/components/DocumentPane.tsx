import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api";
import type { DocText, NodeFinding } from "../types";

interface Props {
  docId: string | null;
  /** Findings keyed by node_id; we surface the leaf ones with non-null evidence. */
  findings: Record<string, NodeFinding | null>;
}

interface Highlight {
  page: number;
  start: number;
  end: number;
  // The class controls colour; "fail" is the demo's loud red.
  cls: "fail" | "pass" | "degraded";
  nodeId: string;
}

const HL_CLASS: Record<Highlight["cls"], string> = {
  fail:     "bg-rose-200 text-rose-900 ring-1 ring-rose-400 rounded px-0.5",
  pass:     "bg-emerald-100 text-emerald-900 ring-1 ring-emerald-300 rounded px-0.5",
  degraded: "bg-amber-100 text-amber-900 ring-1 ring-amber-300 rounded px-0.5",
};

export function DocumentPane({ docId, findings }: Props) {
  const [doc, setDoc] = useState<DocText | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Fetch the doc text whenever the selected doc changes.
  useEffect(() => {
    if (!docId) {
      setDoc(null);
      return;
    }
    setLoading(true);
    setError(null);
    api.getDocText(docId)
      .then(setDoc)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [docId]);

  const highlights = useMemo<Highlight[]>(() => {
    if (!doc) return [];
    return collectHighlights(doc, findings);
  }, [doc, findings]);

  if (!docId) {
    return (
      <Pane>
        <div className="text-slate-500 italic text-sm">Pick a document to see its text here.</div>
      </Pane>
    );
  }
  if (loading) {
    return <Pane><div className="text-slate-500 text-sm">Loading…</div></Pane>;
  }
  if (error) {
    return <Pane><div className="text-rose-700 text-sm font-mono">{error}</div></Pane>;
  }
  if (!doc) return <Pane>{null}</Pane>;

  return (
    <Pane>
      <header className="flex items-baseline gap-3 mb-3">
        <h2 className="text-base font-semibold text-slate-900">{doc.title}</h2>
        <span className="text-xs text-slate-500 font-mono">{doc.id} · {doc.pages.length} pages</span>
        {highlights.length > 0 && (
          <span className="ml-auto text-xs text-slate-500">
            {highlights.length} evidence quote{highlights.length === 1 ? "" : "s"} highlighted
          </span>
        )}
      </header>
      <div ref={containerRef} className="space-y-5 overflow-y-auto pr-2">
        {doc.pages.map((p) => (
          <PageBlock
            key={p.page}
            page={p.page}
            text={p.text}
            highlights={highlights.filter((h) => h.page === p.page)}
          />
        ))}
      </div>
    </Pane>
  );
}

function Pane({ children }: { children: React.ReactNode }) {
  return (
    <section className="bg-white border-t border-slate-200 px-6 py-4 h-full overflow-hidden flex flex-col">
      {children}
    </section>
  );
}

function PageBlock({
  page,
  text,
  highlights,
}: {
  page: number;
  text: string;
  highlights: Highlight[];
}) {
  return (
    <article>
      <div className="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-2">
        Page {page}
      </div>
      <pre className="whitespace-pre-wrap text-sm leading-relaxed font-sans text-slate-800">
        {renderWithHighlights(text, highlights)}
      </pre>
    </article>
  );
}

/* ---------- text/highlight matching ---------- */

function collectHighlights(doc: DocText, findings: Record<string, NodeFinding | null>): Highlight[] {
  const out: Highlight[] = [];
  for (const finding of Object.values(findings)) {
    if (!finding?.check_result?.evidence) continue;
    const evidence = finding.check_result.evidence;
    const cls: Highlight["cls"] = finding.errored
      ? "degraded"
      : finding.passed
        ? "pass"
        : "fail";
    // Try the chunker-resolved page first; fall back to all pages.
    const candidatePages = finding.check_result.page_ref
      ? [finding.check_result.page_ref]
      : doc.pages.map((p) => p.page);

    for (const pageNum of candidatePages) {
      const page = doc.pages.find((p) => p.page === pageNum);
      if (!page) continue;
      const found = findEvidenceSpan(page.text, evidence);
      if (found) {
        out.push({
          page: page.page,
          start: found.start,
          end: found.end,
          cls,
          nodeId: finding.node_id,
        });
        break;
      }
    }
  }
  return out;
}

/** Whitespace-tolerant substring search. Returns indexes into the *original*
 *  text so we can wrap the matched span in <mark> while preserving line breaks. */
function findEvidenceSpan(text: string, needle: string): { start: number; end: number } | null {
  const normNeedle = needle.replace(/\s+/g, " ").trim();
  if (!normNeedle) return null;

  // Build a parallel "compressed" string + index-mapping so we can match in
  // normalized space and recover original indices.
  const map: number[] = [];
  let compressed = "";
  let inWS = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (/\s/.test(ch)) {
      if (!inWS && compressed.length > 0) {
        compressed += " ";
        map.push(i);
      }
      inWS = true;
    } else {
      compressed += ch;
      map.push(i);
      inWS = false;
    }
  }

  const idx = compressed.toLowerCase().indexOf(normNeedle.toLowerCase());
  if (idx < 0) return null;
  const start = map[idx];
  const endChar = idx + normNeedle.length - 1;
  const end = (map[endChar] ?? map[map.length - 1]) + 1;
  return { start, end };
}

function renderWithHighlights(text: string, highlights: Highlight[]): React.ReactNode {
  if (highlights.length === 0) return text;
  // Resolve overlaps by sorting and skipping nested matches.
  const sorted = [...highlights].sort((a, b) => a.start - b.start);
  const segments: React.ReactNode[] = [];
  let cursor = 0;
  for (let i = 0; i < sorted.length; i++) {
    const h = sorted[i];
    if (h.start < cursor) continue; // overlap with previous
    if (h.start > cursor) segments.push(text.slice(cursor, h.start));
    segments.push(
      <mark key={`${h.nodeId}-${h.start}`} className={HL_CLASS[h.cls]}>
        {text.slice(h.start, h.end)}
      </mark>,
    );
    cursor = h.end;
  }
  if (cursor < text.length) segments.push(text.slice(cursor));
  return <>{segments}</>;
}
