import { useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import type { EvaluationGraph, EvaluationGraphEdge, EvaluationGraphNode } from "../api/client";

type Props = {
  graph: EvaluationGraph | null;
  loading: boolean;
  snapshotDate: string;
  onSnapshotChange: (value: string) => void;
  snapshotDates: string[];
  userSearch: string;
  onUserSearchChange: (value: string) => void;
  error: string;
};

const nodeColors: Record<EvaluationGraphNode["type"], string> = {
  user: "#527cf1",
  resource: "#31a77d",
  device: "#a276d2",
};

export default function RelationshipGraph({
  graph,
  loading,
  snapshotDate,
  onSnapshotChange,
  snapshotDates,
  userSearch,
  onUserSearchChange,
  error,
}: Props) {
  const [edgeFilter, setEdgeFilter] = useState("all");
  const [nodeFilter, setNodeFilter] = useState("all");
  const [selectedEdge, setSelectedEdge] = useState<EvaluationGraphEdge | null>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [drag, setDrag] = useState<{ x: number; y: number; startX: number; startY: number } | null>(null);
  const graphRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const graphElement = graphRef.current;
    if (!graphElement) return;
    const handleWheel = (event: globalThis.WheelEvent) => {
      event.preventDefault();
      setZoom((current) => Math.min(Math.max(current * (event.deltaY < 0 ? 1.1 : 0.9), 0.55), 2.5));
    };
    graphElement.addEventListener("wheel", handleWheel, { passive: false });
    return () => graphElement.removeEventListener("wheel", handleWheel);
  }, []);

  const visible = useMemo(() => {
    const nodes = graph?.nodes.filter((node) =>
      nodeFilter === "all" || node.type === nodeFilter
    ) ?? [];
    const nodeIds = new Set(nodes.map((node) => node.id));
    const edges = graph?.edges.filter((edge) =>
      nodeIds.has(edge.source)
      && nodeIds.has(edge.target)
      && (edgeFilter === "all" || edge.type === edgeFilter)
    ) ?? [];
    const nodePositions = new Map<string, { x: number; y: number }>();
    for (const type of ["user", "resource", "device"] as const) {
      const nodesOfType = nodes.filter((node) => node.type === type);
      const x = type === "user" ? 150 : type === "resource" ? 500 : 850;
      nodesOfType.forEach((node, index) => {
        nodePositions.set(node.id, {
          x,
          y: 48 + (nodesOfType.length < 2 ? 0 : (index * 504) / (nodesOfType.length - 1)),
        });
      });
    }
    return { nodes, edges, nodePositions };
  }, [graph, nodeFilter, edgeFilter]);

  function startDrag(event: PointerEvent<SVGSVGElement>) {
    if (event.target !== event.currentTarget) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setDrag({ x: event.clientX, y: event.clientY, startX: pan.x, startY: pan.y });
  }

  function moveDrag(event: PointerEvent<SVGSVGElement>) {
    if (drag) {
      setPan({
        x: drag.startX + event.clientX - drag.x,
        y: drag.startY + event.clientY - drag.y,
      });
    }
  }

  const labelsVisible = (node: EvaluationGraphNode, index: number) => {
    const typeCount = visible.nodes.filter((candidate) => candidate.type === node.type).length;
    const labelStep = Math.max(Math.ceil(typeCount / 18), 1);
    return (Boolean(userSearch) && typeCount <= 30) || index % labelStep === 0;
  };

  return (
    <div className="relationship-graph-panel">
      <div className="graph-controls">
        <label className="field-label">Historical snapshot
          <select value={snapshotDate} onChange={(event) => onSnapshotChange(event.target.value)}>
            <option value="">All observed history</option>
            {snapshotDates.map((date) => <option value={date} key={date}>{date}</option>)}
          </select>
        </label>
        <label className="field-label">Search user / entity
          <input value={userSearch} onChange={(event) => onUserSearchChange(event.target.value)} placeholder="Filter observed relationships" />
        </label>
        <label className="field-label">Relationship
          <select value={edgeFilter} onChange={(event) => setEdgeFilter(event.target.value)}>
            <option value="all">All observed relationships</option>
            <option value="user-resource">User-to-resource</option>
            <option value="user-device">User-to-device</option>
          </select>
        </label>
        <label className="field-label">Node type
          <select value={nodeFilter} onChange={(event) => setNodeFilter(event.target.value)}>
            <option value="all">All supported types</option>
            <option value="user">Users</option>
            <option value="resource">Resources</option>
            <option value="device">Devices</option>
          </select>
        </label>
      </div>
      <div className="graph-legend">
        {Object.entries(nodeColors).map(([type, color]) => <span key={type}><i style={{ background: color }} />{type}</span>)}
        <span><i className="graph-edge-key" />Observed interaction</span>
        <div><button className="button subtle" onClick={() => setZoom((current) => Math.min(current + 0.15, 2.5))} aria-label="Zoom in">+</button><button className="button subtle" onClick={() => setZoom((current) => Math.max(current - 0.15, 0.55))} aria-label="Zoom out">−</button><button className="button subtle" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }} aria-label="Reset graph view">Reset</button></div>
      </div>
      {error && <p className="small error-text">{error}</p>}
      {loading ? <div className="graph-empty">Loading relationships from processed activity…</div> : graph && visible.edges.length ? (
        <svg
          className="relationship-graph"
          viewBox="0 0 1000 600"
          ref={graphRef}
          role="img"
          aria-label="Interactive graph of observed users, resources, and devices"
          onPointerDown={startDrag}
          onPointerMove={moveDrag}
          onPointerUp={() => setDrag(null)}
          onPointerCancel={() => setDrag(null)}
        >
          <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
            {visible.edges.map((edge) => {
              const from = visible.nodePositions.get(edge.source);
              const to = visible.nodePositions.get(edge.target);
              if (!from || !to) return null;
              const active = selectedEdge?.id === edge.id;
              return <g key={edge.id} className="graph-edge" onClick={() => setSelectedEdge(edge)}>
                <title>{`${edge.label}: ${edge.event_count} observed event(s)`}</title>
                <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke={active ? "#e19a40" : edge.type === "user-resource" ? "#6fae92" : "#a58ac7"} strokeWidth={active ? 3 : Math.min(1 + Math.log2(edge.event_count + 1) / 2, 4)} opacity={active ? 0.9 : 0.45} />
                <text x={(from.x + to.x) / 2} y={(from.y + to.y) / 2 - 4} className="graph-edge-label">{`${edge.type === "user-resource" ? "resource" : "device"} · ${edge.event_count}`}</text>
              </g>;
            })}
            {visible.nodes.map((node, index) => {
              const position = visible.nodePositions.get(node.id);
              if (!position) return null;
              return <g key={node.id} className="graph-node">
                <title>{`${node.type}: ${node.label}`}</title>
                <circle cx={position.x} cy={position.y} r="7" fill={nodeColors[node.type]} />
                {labelsVisible(node, index) && <text x={position.x + (node.type === "user" ? -12 : 12)} y={position.y + 3} textAnchor={node.type === "user" ? "end" : "start"} className="graph-node-label">{node.label.length > 27 ? `${node.label.slice(0, 24)}…` : node.label}</text>}
              </g>;
            })}
          </g>
        </svg>
      ) : <div className="graph-empty">{graph ? "No recorded relationships match these graph filters." : "No evaluation results available"}</div>}
      {graph?.truncated && <p className="small muted">The display is limited to the most frequently observed relationships. Counts above are dataset totals; search or select a snapshot to inspect a smaller view.</p>}
      {selectedEdge && <div className="relationship-inspection"><strong>Relationship inspection</strong><span>{selectedEdge.label} · {selectedEdge.event_count.toLocaleString()} observed event(s)</span><small>{selectedEdge.source.replace("user:", "User · ").replace("resource:", "Resource · ").replace("device:", "Device · ")} → {selectedEdge.target.replace("user:", "User · ").replace("resource:", "Resource · ").replace("device:", "Device · ")}</small></div>}
      <div className="graph-counts">
        <span>Users <strong>{graph?.node_counts.user.toLocaleString() ?? "0"}</strong></span>
        <span>Resources <strong>{graph?.node_counts.resource.toLocaleString() ?? "0"}</strong></span>
        <span>Devices <strong>{graph?.node_counts.device.toLocaleString() ?? "0"}</strong></span>
        <span>Relationships <strong>{graph?.relationship_count.toLocaleString() ?? "0"}</strong></span>
        <span>Density <strong>{graph?.graph_density == null ? "—" : `${(graph.graph_density * 100).toFixed(2)}%`}</strong></span>
        <span>Snapshots <strong>{graph?.snapshot_count.toLocaleString() ?? snapshotDates.length}</strong></span>
      </div>
    </div>
  );
}
