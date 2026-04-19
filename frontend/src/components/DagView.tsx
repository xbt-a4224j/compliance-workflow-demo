import { useMemo } from "react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  type Node as RFNode,
  type Edge as RFEdge,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
} from "reactflow";
import "reactflow/dist/style.css";

import type {
  ExecutionGraph,
  GraphNode,
  NodeFinding,
  NodeStatus,
  RuleSummary,
  RunResult,
} from "../types";
import { NodeCard } from "./NodeCard";

interface Props {
  graph: ExecutionGraph;
  rules: RuleSummary[];
  statuses: Record<string, NodeStatus>;
  findings: Record<string, NodeFinding | null>;
  result: RunResult | null;
  // False when the DAG is shown purely for inspection (e.g. Rules view):
  // tiles render without per-node status pills and skip the lane-header
  // verdict pill too, since nothing is being executed.
  showStatus?: boolean;
}

interface NodeData {
  node: GraphNode;
  status: NodeStatus;
  finding: NodeFinding | null;
  showStatus: boolean;
}

interface LaneHeaderData {
  ruleId: string;
  ruleName: string;
  width: number;
  status: "pending" | "passed" | "failed" | "degraded" | "running";
  showStatus: boolean;
}

/* ---------- layout constants (hoisted so node-renderers can use them) ---------- */

const NODE_W = 280;
const X_GAP = 60;
const Y_GAP = 200;       // generous so cards with multi-line evidence don't overlap
const LANE_GAP = 80;
const HEADER_H = 104;    // fits two lines of text-base + the ruleId line + padding
const LANE_HEADER_OFFSET = 16;
const CARD_RESERVED = 280; // estimated tall-card height for layout buffer

const dagNode = ({ data }: { data: NodeData }) => (
  <>
    <Handle type="target" position={Position.Top} className="!bg-slate-400" />
    <NodeCard
      node={data.node}
      status={data.status}
      finding={data.finding}
      showStatus={data.showStatus}
    />
    <Handle type="source" position={Position.Bottom} className="!bg-slate-400" />
  </>
);

const STATUS_PILL: Record<LaneHeaderData["status"], string> = {
  pending:  "bg-slate-100 text-slate-600 border-slate-300",
  running:  "bg-sky-100 text-sky-800 border-sky-300",
  passed:   "bg-emerald-100 text-emerald-800 border-emerald-300",
  failed:   "bg-rose-100 text-rose-800 border-rose-300",
  degraded: "bg-amber-100 text-amber-800 border-amber-300",
};

const STATUS_LABEL: Record<LaneHeaderData["status"], string> = {
  pending: "Pending", running: "Running", passed: "Pass", failed: "Fail", degraded: "Degraded",
};

const laneHeader = ({ data }: { data: LaneHeaderData }) => (
  <div
    className="px-4 py-3 bg-white border-l-4 border-slate-300 rounded-r shadow-sm
               flex items-start justify-between gap-3"
    style={{ width: data.width, height: HEADER_H }}
  >
    <div className="min-w-0 flex-1">
      <div className="text-xs uppercase tracking-wider text-slate-500 font-semibold font-mono">
        {data.ruleId}
      </div>
      <div className="text-base font-medium text-slate-900 leading-snug break-words">
        {data.ruleName}
      </div>
    </div>
    {data.showStatus && (
      <span className={`shrink-0 px-3 py-1 text-sm font-semibold rounded border ${STATUS_PILL[data.status]}`}>
        {STATUS_LABEL[data.status]}
      </span>
    )}
  </div>
);

const laneSeparator = ({ data }: { data: { height: number } }) => (
  <div style={{ height: data.height, width: 2 }} className="bg-slate-200" />
);

const nodeTypes = { dagNode, laneHeader, laneSeparator };

export function DagView(props: Props) {
  // Wrap the inner component so useReactFlow has a provider context.
  return (
    <ReactFlowProvider>
      <DagViewInner {...props} />
    </ReactFlowProvider>
  );
}

function DagViewInner({ graph, rules, statuses, findings, result, showStatus = true }: Props) {
  const { nodes, edges } = useMemo(
    () => buildSwimlanes(graph, rules, statuses, findings, result, showStatus),
    [graph, rules, statuses, findings, result, showStatus],
  );
  const rf = useReactFlow();

  // Arrow-key horizontal pan. Captured at the wrapper div so it works as
  // long as the user has clicked into the canvas area.
  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const STEP = 120;
    if (e.key === "ArrowLeft") {
      const v = rf.getViewport();
      rf.setViewport({ ...v, x: v.x + STEP }, { duration: 150 });
    } else if (e.key === "ArrowRight") {
      const v = rf.getViewport();
      rf.setViewport({ ...v, x: v.x - STEP }, { duration: 150 });
    } else if (e.key === "ArrowUp") {
      const v = rf.getViewport();
      rf.setViewport({ ...v, y: v.y + STEP }, { duration: 150 });
    } else if (e.key === "ArrowDown") {
      const v = rf.getViewport();
      rf.setViewport({ ...v, y: v.y - STEP }, { duration: 150 });
    } else {
      return;
    }
    e.preventDefault();
  };

  return (
    <div className="w-full h-full outline-none" tabIndex={0} onKeyDown={onKeyDown}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.08 }}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        minZoom={0.2}
        panOnScroll
      >
        <Background color="#cbd5e1" gap={28} size={1} />
        <Controls className="!bg-white !border-slate-300 !shadow-sm" />
      </ReactFlow>
    </div>
  );
}

/* ---------- horizontal swimlane layout ---------- */

function buildSwimlanes(
  graph: ExecutionGraph,
  rules: RuleSummary[],
  statuses: Record<string, NodeStatus>,
  findings: Record<string, NodeFinding | null>,
  result: RunResult | null,
  showStatus: boolean,
): { nodes: RFNode[]; edges: RFEdge[] } {
  const ruleToNodes = collectRuleSubgraphs(graph);
  const orderedRules = orderedRuleIds(graph, rules);

  // Lay lanes left-to-right. Each lane has its own internal top-down DAG
  // (root on top → leaves on bottom). xCursor tracks the left edge of the
  // next lane.
  const positions: Record<string, { x: number; y: number }> = {};
  const ownerLane: Record<string, number> = {};
  const laneHeaders: { ruleId: string; ruleName: string; leftX: number; width: number }[] = [];
  const separators: { x: number }[] = [];
  let xCursor = 0;
  let maxContentBottom = HEADER_H + LANE_HEADER_OFFSET; // tallest lane y-extent

  orderedRules.forEach((ruleId, laneIndex) => {
    const nodesInLane = Array.from(ruleToNodes[ruleId]).filter(
      (id) => ownerLane[id] === undefined,
    );
    const layers = computeLayers(graph, nodesInLane);
    const maxLayer = nodesInLane.length === 0 ? 0 : Math.max(...nodesInLane.map((n) => layers[n] ?? 0));

    const byLayer: Record<number, string[]> = {};
    nodesInLane.forEach((id) => {
      const l = layers[id] ?? 0;
      (byLayer[l] ??= []).push(id);
    });

    let laneWidth = NODE_W;
    Object.values(byLayer).forEach((ids) => {
      const w = ids.length * NODE_W + (ids.length - 1) * X_GAP;
      laneWidth = Math.max(laneWidth, w);
    });

    const laneLeft = xCursor;
    const dagTopY = HEADER_H + LANE_HEADER_OFFSET;

    Object.entries(byLayer).forEach(([layerStr, ids]) => {
      const layer = Number(layerStr);
      const y = dagTopY + (maxLayer - layer) * Y_GAP;
      const totalWidth = ids.length * NODE_W + (ids.length - 1) * X_GAP;
      const xStart = laneLeft + (laneWidth - totalWidth) / 2;
      ids.forEach((id, i) => {
        positions[id] = { x: xStart + i * (NODE_W + X_GAP), y };
        ownerLane[id] = laneIndex;
      });
    });

    // Track the deepest extent across all lanes so separators (and any future
    // background overlay) cover exactly the rendered content — no over-tall
    // separator skewing fitView.
    const laneBottom = dagTopY + maxLayer * Y_GAP + CARD_RESERVED;
    if (laneBottom > maxContentBottom) maxContentBottom = laneBottom;

    const ruleObj = rules.find((r) => r.id === ruleId);
    laneHeaders.push({
      ruleId,
      ruleName: ruleObj?.name ?? ruleId,
      leftX: laneLeft,
      width: laneWidth,
    });

    xCursor = laneLeft + laneWidth + LANE_GAP;

    // Separator between this lane and the next (skip after the final lane).
    if (laneIndex < orderedRules.length - 1) {
      separators.push({ x: xCursor - LANE_GAP / 2 });
    }
  });

  const nodes: RFNode[] = [];

  // Lane separators: thin vertical rules between columns. Explicit width/height
  // on the node object so react-flow knows their bounds for fitView (without
  // these, react-flow has to measure them post-render and they get skipped on
  // the first fit, leaving headers/aggregators off-screen).
  separators.forEach((s, i) => {
    nodes.push({
      id: `lane-sep-${i}`,
      type: "laneSeparator",
      position: { x: s.x - 1, y: 0 },
      data: { height: maxContentBottom },
      width: 2,
      height: maxContentBottom,
      draggable: false,
      selectable: false,
      zIndex: -1,
    });
  });

  laneHeaders.forEach((h) => {
    const status = ruleStatus(h.ruleId, result, statuses, ruleToNodes[h.ruleId]);
    nodes.push({
      id: `lane-header-${h.ruleId}`,
      type: "laneHeader",
      position: { x: h.leftX, y: 0 },
      data: { ruleId: h.ruleId, ruleName: h.ruleName, width: h.width, status, showStatus },
      width: h.width,
      height: HEADER_H,
      draggable: false,
      selectable: false,
    });
  });

  Object.values(graph.nodes).forEach((n) => {
    if (positions[n.id] === undefined) return;
    nodes.push({
      id: n.id,
      type: "dagNode",
      position: positions[n.id],
      data: {
        node: n,
        status: statuses[n.id] ?? "pending",
        finding: findings[n.id] ?? null,
        showStatus,
      } as NodeData,
      width: NODE_W,
      // Reserved height tracks tallest possible card; over-spec here is
      // harmless (react-flow uses it for layout bounds, not visual size).
      height: CARD_RESERVED,
      draggable: false,
    });
  });

  const edges: RFEdge[] = [];
  for (const node of Object.values(graph.nodes)) {
    if (positions[node.id] === undefined) continue;
    for (const childId of node.child_ids) {
      if (positions[childId] === undefined) continue;
      const crossLane = ownerLane[node.id] !== ownerLane[childId];
      edges.push({
        id: `${node.id}->${childId}`,
        source: node.id,
        target: childId,
        animated: statuses[childId] === "running",
        markerEnd: { type: MarkerType.ArrowClosed, color: crossLane ? "#0284c7" : "#94a3b8" },
        style: {
          stroke: crossLane ? "#0284c7" : "#94a3b8",
          strokeWidth: crossLane ? 2 : 1.75,
          strokeDasharray: crossLane ? "6 4" : undefined,
        },
      });
    }
  }

  return { nodes, edges };
}

function collectRuleSubgraphs(graph: ExecutionGraph): Record<string, Set<string>> {
  const out: Record<string, Set<string>> = {};
  for (const [ruleId, rootId] of Object.entries(graph.roots)) {
    const visited = new Set<string>();
    const stack = [rootId];
    while (stack.length > 0) {
      const id = stack.pop()!;
      if (visited.has(id)) continue;
      visited.add(id);
      const node = graph.nodes[id];
      if (node) stack.push(...node.child_ids);
    }
    out[ruleId] = visited;
  }
  return out;
}

function orderedRuleIds(graph: ExecutionGraph, rules: RuleSummary[]): string[] {
  // Render rules in the order the backend listed them — gives the demo
  // a deterministic layout.
  const ruleOrder = rules.map((r) => r.id).filter((rid) => graph.roots[rid] !== undefined);
  // Include any rules in graph.roots not in the rules list (defensive).
  for (const rid of Object.keys(graph.roots)) {
    if (!ruleOrder.includes(rid)) ruleOrder.push(rid);
  }
  return ruleOrder;
}

/** Layer = longest path to a leaf descendant (leaves=0). Operates only on
 *  the provided node subset so the layout stays per-lane. */
function computeLayers(graph: ExecutionGraph, ids: string[]): Record<string, number> {
  const layers: Record<string, number> = {};
  const inSet = new Set(ids);
  for (const id of graph.topo_order) {
    if (!inSet.has(id)) continue;
    const node = graph.nodes[id];
    const childLayers = node.child_ids.filter((c) => inSet.has(c)).map((c) => layers[c] ?? 0);
    layers[id] = childLayers.length === 0 ? 0 : 1 + Math.max(...childLayers);
  }
  return layers;
}

function ruleStatus(
  ruleId: string,
  result: RunResult | null,
  statuses: Record<string, NodeStatus>,
  laneNodes: Set<string>,
): LaneHeaderData["status"] {
  if (result) {
    if (result.per_rule_errored[ruleId]) return "degraded";
    return result.per_rule[ruleId] ? "passed" : "failed";
  }
  // No final result yet — derive from in-flight node statuses.
  const states = Array.from(laneNodes).map((id) => statuses[id] ?? "pending");
  if (states.some((s) => s === "running")) return "running";
  if (states.every((s) => s === "pending")) return "pending";
  if (states.some((s) => s === "failed")) return "failed";
  if (states.some((s) => s === "degraded")) return "degraded";
  if (states.every((s) => s === "passed")) return "passed";
  return "running";
}
