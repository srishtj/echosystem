'use client';

import dynamic from 'next/dynamic';
import { useEffect, useMemo, useRef, useState } from 'react';
import useSWR from 'swr';
import { API_URL, apiFetch } from '../lib/api';

const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), { ssr: false });

const fetcher = (url: string) => apiFetch(url).then((r) => r.json());

type ApiNode = { name: string; type: string };
type ApiEdge = { source: string; target: string; relation: string };

type GraphNodeDatum = { id: string; group: string };
type GraphLinkDatum = { source: string; target: string; label: string };

const TYPE_COLORS: Record<string, string> = {
  Company: '#7a1f2e',
  Person: '#a9793a',
  Material: '#3f6b4a',
  Product: '#4a5a73',
};
const DEFAULT_COLOR = '#9c8b76';
const DIM_COLOR = 'rgba(156, 139, 118, 0.18)';

function colorForType(type: string): string {
  return TYPE_COLORS[type] ?? DEFAULT_COLOR;
}

export default function GraphView({
  highlightEntities,
  onNodeClick,
}: {
  highlightEntities?: string[];
  onNodeClick?: (name: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const graphRef = useRef<any>(null);
  const [size, setSize] = useState({ width: 0, height: 560 });
  const [searchTerm, setSearchTerm] = useState('');
  const [hoverNode, setHoverNode] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });

  useEffect(() => {
    if (highlightEntities && highlightEntities.length > 0) {
      setSearchTerm('');
      setSelectedNode(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [highlightEntities]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      setSize((s) => ({ ...s, width: entry.contentRect.width }));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const { data, error } = useSWR<{ nodes: ApiNode[]; edges: ApiEdge[] }>(
    `${API_URL}/api/graph`,
    fetcher,
    { refreshInterval: 15000 }
  );

  const graphData = useMemo(() => {
    if (!data) return { nodes: [] as GraphNodeDatum[], links: [] as GraphLinkDatum[] };
    const nodeIds = new Set(data.nodes.map((n) => n.name));
    return {
      nodes: data.nodes.map((n) => ({ id: n.name, group: n.type })),
      // A link referencing a node outside the current node set crashes
      // react-force-graph's internal resolution, so drop any such links.
      links: data.edges
        .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
        .map((e) => ({ source: e.source, target: e.target, label: e.relation })),
    };
  }, [data]);

  const neighborMap = useMemo(() => {
    const map = new Map<string, Set<string>>();
    for (const node of graphData.nodes) map.set(node.id, new Set());
    for (const link of graphData.links) {
      const src = typeof link.source === 'string' ? link.source : (link.source as { id: string }).id;
      const tgt = typeof link.target === 'string' ? link.target : (link.target as { id: string }).id;
      map.get(src)?.add(tgt);
      map.get(tgt)?.add(src);
    }
    return map;
  }, [graphData]);

  const searchMatches = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    if (!term) return new Set<string>();
    return new Set(graphData.nodes.filter((n) => n.id.toLowerCase().includes(term)).map((n) => n.id));
  }, [searchTerm, graphData]);

  const persistentFocusIds = useMemo(() => {
    const ids = new Set<string>();
    if (searchTerm.trim()) {
      searchMatches.forEach((id) => ids.add(id));
    } else if (selectedNode) {
      ids.add(selectedNode);
    }
    (highlightEntities ?? []).forEach((id) => ids.add(id));
    return ids;
  }, [selectedNode, searchMatches, searchTerm, highlightEntities]);

  const expandWithNeighbors = (base: Set<string>) => {
    const expanded = new Set(base);
    base.forEach((id) => neighborMap.get(id)?.forEach((n) => expanded.add(n)));
    return expanded;
  };

  const activeFocusIds = useMemo(() => {
    const base = hoverNode ? new Set([hoverNode]) : persistentFocusIds;
    if (base.size === 0) return null;
    return expandWithNeighbors(base);
  }, [hoverNode, persistentFocusIds, neighborMap]);

  const persistentFocusExpanded = useMemo(
    () => expandWithNeighbors(persistentFocusIds),
    [persistentFocusIds, neighborMap]
  );

  useEffect(() => {
    if (!graphRef.current) return;
    if (persistentFocusExpanded.size > 0) {
      graphRef.current.zoomToFit(500, 80, (node: { id?: string | number }) =>
        persistentFocusExpanded.has(String(node.id))
      );
    }
  }, [persistentFocusExpanded]);

  useEffect(() => {
    if (data && graphRef.current) {
      const t = setTimeout(() => graphRef.current?.zoomToFit(400, 40), 300);
      return () => clearTimeout(t);
    }
  }, [data]);

  const hoveredEntity = hoverNode ?? selectedNode;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="text"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          placeholder="Search entities..."
          className="w-56 rounded-lg border border-hairline bg-cream px-3 py-1.5 text-sm text-ink outline-none placeholder:text-ink-muted/70 focus:border-accent focus:ring-2 focus:ring-accent-soft"
        />
        {searchTerm && (
          <span className="text-xs text-ink-muted">{searchMatches.size} match(es)</span>
        )}
        <div className="flex items-center gap-3 text-xs text-ink-muted">
          {Object.entries(TYPE_COLORS).map(([type, color]) => (
            <span key={type} className="flex items-center gap-1">
              <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
              {type}
            </span>
          ))}
        </div>
      </div>

      <div
        ref={containerRef}
        onMouseMove={(e) => {
          const rect = containerRef.current?.getBoundingClientRect();
          if (rect) setMousePos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
        }}
        className="relative h-[560px] w-full overflow-hidden rounded-xl border border-hairline bg-cream"
      >
        {error && <p className="p-3 text-sm text-negative">Failed to load graph.</p>}
        {!error && !data && <p className="p-3 text-sm text-ink-muted">Loading graph...</p>}
        {!error && data && data.nodes.length === 0 && (
          <p className="p-3 text-sm text-ink-muted">
            The graph is empty — search a topic above to pull in real articles and populate it.
          </p>
        )}

        {!error && data && data.nodes.length > 0 && size.width > 0 && (
          <ForceGraph2D
            ref={graphRef}
            width={size.width}
            height={size.height}
            graphData={graphData}
            nodeRelSize={5}
            onBackgroundClick={() => setSelectedNode(null)}
            onNodeHover={(node) => setHoverNode(node ? String(node.id) : null)}
            onNodeClick={(node) => {
              const id = String(node.id);
              setSearchTerm('');
              setSelectedNode((prev) => (prev === id ? null : id));
              onNodeClick?.(id);
            }}
            nodeCanvasObject={(node, ctx, globalScale) => {
              const id = String(node.id);
              const focused = !activeFocusIds || activeFocusIds.has(id);
              const isPrimary = id === hoverNode || id === selectedNode || persistentFocusIds.has(id);
              const radius = isPrimary ? 7 : 5;
              const color = focused ? colorForType(String((node as GraphNodeDatum).group)) : DIM_COLOR;

              ctx.beginPath();
              ctx.arc(node.x ?? 0, node.y ?? 0, radius, 0, 2 * Math.PI);
              ctx.fillStyle = color;
              ctx.fill();

              if (isPrimary) {
                ctx.lineWidth = 1.5 / globalScale;
                ctx.strokeStyle = '#2a1e17';
                ctx.stroke();
              }

              if (isPrimary || (globalScale > 3 && focused)) {
                const label = id;
                const fontSize = 12 / globalScale;
                ctx.font = `${fontSize}px sans-serif`;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'top';
                ctx.fillStyle = '#2a1e17';
                ctx.fillText(label, node.x ?? 0, (node.y ?? 0) + radius + 2);
              }
            }}
            nodePointerAreaPaint={(node, color, ctx) => {
              ctx.beginPath();
              ctx.arc(node.x ?? 0, node.y ?? 0, 7, 0, 2 * Math.PI);
              ctx.fillStyle = color;
              ctx.fill();
            }}
            linkColor={(link) => {
              if (!activeFocusIds) return 'rgba(156, 139, 118, 0.4)';
              const src = typeof link.source === 'string' ? link.source : (link.source as { id: string }).id;
              const tgt = typeof link.target === 'string' ? link.target : (link.target as { id: string }).id;
              return activeFocusIds.has(src) && activeFocusIds.has(tgt)
                ? 'rgba(122, 31, 46, 0.75)'
                : 'rgba(156, 139, 118, 0.08)';
            }}
            linkWidth={(link) => {
              if (!activeFocusIds) return 1;
              const src = typeof link.source === 'string' ? link.source : (link.source as { id: string }).id;
              const tgt = typeof link.target === 'string' ? link.target : (link.target as { id: string }).id;
              return activeFocusIds.has(src) && activeFocusIds.has(tgt) ? 2 : 0.5;
            }}
            linkDirectionalParticles={(link) => {
              if (!activeFocusIds) return 0;
              const src = typeof link.source === 'string' ? link.source : (link.source as { id: string }).id;
              const tgt = typeof link.target === 'string' ? link.target : (link.target as { id: string }).id;
              return activeFocusIds.has(src) && activeFocusIds.has(tgt) ? 3 : 0;
            }}
            linkDirectionalParticleWidth={2}
            linkDirectionalParticleColor={() => '#7a1f2e'}
          />
        )}

        {hoveredEntity && (
          <div
            className="pointer-events-none absolute z-10 max-w-xs rounded-lg border border-accent-dark/40 bg-ink/95 px-3 py-2 text-xs text-cream shadow-lg"
            style={{ left: mousePos.x + 14, top: mousePos.y + 14 }}
          >
            <div className="font-semibold">{hoveredEntity}</div>
            <div className="text-cream/70">
              {graphData.nodes.find((n) => n.id === hoveredEntity)?.group ?? 'Entity'} &middot;{' '}
              {neighborMap.get(hoveredEntity)?.size ?? 0} connection(s)
            </div>
            <div className="mt-1 text-cream/50">Click for full details</div>
          </div>
        )}
      </div>
    </div>
  );
}
