import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import type {
  ExecutionGraph,
  NodeStatus,
  OrchestratorEvent,
  RunResult,
} from "../types";

export interface RunStreamState {
  /** node_id → current lifecycle status */
  statuses: Record<string, NodeStatus>;
  /** node_id → finding once available (leaves and aggregators alike) */
  findings: Record<string, OrchestratorEvent["finding"]>;
  /** Final RunResult after run_finished arrives. */
  result: RunResult | null;
  /** Connection state for the SSE stream. */
  connectionState: "idle" | "connecting" | "open" | "closed" | "error";
  /** Chronological list of events for the debug log panel. */
  events: OrchestratorEvent[];
}

const initialState = (graph: ExecutionGraph | null): RunStreamState => ({
  statuses: graph
    ? Object.fromEntries(Object.keys(graph.nodes).map((id) => [id, "pending" as NodeStatus]))
    : {},
  findings: {},
  result: null,
  connectionState: "idle",
  events: [],
});

/**
 * Subscribe to /runs/:id/stream and accumulate per-node status + final result.
 *
 * Initial statuses are seeded "pending" for every node in the DAG passed in,
 * so the UI can render the full DAG immediately and tiles flip as events
 * arrive. That's the demo's headline UX (#19 + #17 contract).
 */
export function useRunStream(
  runId: string | null,
  graph: ExecutionGraph | null,
): RunStreamState {
  const [state, setState] = useState<RunStreamState>(() => initialState(graph));
  const sourceRef = useRef<EventSource | null>(null);

  // Reset state when run_id or graph changes (e.g. starting a new run).
  useEffect(() => {
    setState(initialState(graph));
  }, [runId, graph]);

  useEffect(() => {
    if (!runId) return;

    const source = new EventSource(api.streamUrl(runId));
    sourceRef.current = source;
    setState((s) => ({ ...s, connectionState: "connecting" }));

    source.onopen = () => {
      setState((s) => ({ ...s, connectionState: "open" }));
    };

    const handleEvent = (raw: MessageEvent) => {
      let parsed: OrchestratorEvent;
      try {
        parsed = JSON.parse(raw.data);
      } catch {
        return; // skip malformed frames silently
      }
      setState((prev) => applyEvent(prev, parsed));
      if (parsed.kind === "run_finished") {
        source.close();
        setState((s) => ({ ...s, connectionState: "closed" }));
      }
    };

    // Server sets event: <kind> on every frame. Listen for each kind separately
    // because EventSource's default 'message' handler only fires when the
    // server omits the event: line — which we don't.
    const kinds: OrchestratorEvent["kind"][] = [
      "run_started",
      "check_started",
      "check_finished",
      "run_finished",
    ];
    kinds.forEach((kind) => source.addEventListener(kind, handleEvent as EventListener));

    source.onerror = () => {
      // EventSource auto-reconnects; flag the state so the UI can show a hint.
      setState((s) => ({
        ...s,
        connectionState: s.connectionState === "closed" ? "closed" : "error",
      }));
    };

    return () => {
      source.close();
      sourceRef.current = null;
    };
  }, [runId]);

  return state;
}

function applyEvent(prev: RunStreamState, event: OrchestratorEvent): RunStreamState {
  const next: RunStreamState = {
    ...prev,
    events: [...prev.events, event],
  };

  if (event.kind === "check_started" && event.node_id) {
    next.statuses = { ...prev.statuses, [event.node_id]: "running" };
  }

  if (event.kind === "check_finished" && event.node_id && event.finding) {
    const status: NodeStatus = event.finding.errored
      ? "degraded"
      : event.finding.passed
        ? "passed"
        : "failed";
    next.statuses = { ...prev.statuses, [event.node_id]: status };
    next.findings = { ...prev.findings, [event.node_id]: event.finding };
  }

  if (event.kind === "run_finished" && event.result) {
    next.result = event.result;
  }

  return next;
}
