"use client";

import { Background, Handle, MarkerType, Position, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import { useMemo } from "react";
import type { Policy, Tool, Verify } from "@/lib/types";

type ToolNodeData = { tool: Tool; mode?: string; rule?: string; onPath: boolean };

function ToolNode({ data }: NodeProps<Node<ToolNodeData>>) {
  const { tool, mode, rule, onPath } = data;
  return (
    <div className="node" data-onpath={onPath} data-mode={mode ?? "allow"}>
      <Handle type="target" position={Position.Left} />
      <span className="node-name">{tool.tool}</span>
      <span className="node-meta">
        {(["U", "S", "X"] as const).map((leg) => (
          <span key={leg} className="leg" data-on={tool.legs[leg]}>
            {leg}
          </span>
        ))}
        {mode && (
          <span className="chip" data-d={mode === "deny" ? "deny" : mode === "approval" ? "approval" : "allow"}>
            {mode}
          </span>
        )}
      </span>
      {rule && <span className="node-rule">{rule}</span>}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

const nodeTypes = { tool: ToolNode };
const STEERABLE = ["object_id", "destination"];

function column(tool: Tool): number {
  if (tool.legs.U) return 0;
  if (tool.legs.S) return 1;
  return 2;
}

export function ToolGraph({ catalog, policy, verify, after, cutAt }: {
  catalog: Tool[];
  policy: Policy;
  verify: Verify;
  after: boolean;
  /** First tool on the attack path the policy refused (from the recorded run). */
  cutAt?: string;
}) {
  const { nodes, edges } = useMemo(() => {
    const rules = policy.agents[0].tools;
    const path = verify.reachability_before.path;
    const rows = [0, 0, 0];
    const nodes: Node<ToolNodeData>[] = catalog.map((tool) => {
      const col = column(tool);
      const y = rows[col]++ * 130 + (col === 0 ? 150 : 20);
      const rule = rules[tool.tool];
      const constraint = rule?.constraints?.map((c) => `${c.arg} ${c.op === "eq" ? "==" : "∈"} ${c.ctx}`).join(" · ");
      return {
        id: tool.tool,
        type: "tool",
        position: { x: col * 330, y },
        data: {
          tool,
          mode: after ? rule?.mode ?? "deny" : undefined,
          rule: after ? constraint : undefined,
          onPath: !after && path.includes(tool.tool),
        },
      };
    });

    const edges: Edge[] = [];
    for (const src of catalog) {
      for (const dst of catalog) {
        if (src === dst) continue;
        const flows =
          (src.legs.U && dst.legs.S && dst.args.some((a) => a.role === "object_id" || a.role === "filter")) ||
          (src.legs.S && dst.legs.X && dst.args.some((a) => STEERABLE.includes(a.role)));
        if (!flows) continue;
        const i = path.indexOf(src.tool);
        const onPath = i >= 0 && path[i + 1] === dst.tool;
        const cut = after && onPath && dst.tool === cutAt;
        edges.push({
          id: `${src.tool}->${dst.tool}`,
          source: src.tool,
          target: dst.tool,
          animated: onPath && !after,
          label: cut ? "cut" : undefined,
          markerEnd: { type: MarkerType.ArrowClosed },
          style: onPath
            ? { stroke: after ? "var(--color-muted)" : "var(--color-danger)", strokeWidth: 2.5,
                strokeDasharray: after ? "6 6" : undefined }
            : { stroke: "var(--color-rule-strong)", strokeWidth: 1 },
        });
      }
    }
    return { nodes, edges };
  }, [catalog, policy, verify, after, cutAt]);

  return (
    <div className="map" aria-label="Tool data-flow graph">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        nodesDraggable={false}
        nodesConnectable={false}
        proOptions={{ hideAttribution: true }}
        minZoom={0.4}
      >
        <Background gap={24} color="var(--color-rule)" />
      </ReactFlow>
    </div>
  );
}
