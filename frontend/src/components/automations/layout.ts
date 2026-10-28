import type { Step, StepPath } from '@/components/automations/model';

/** Card geometry on the canvas; connectors leave and enter cards at PORT_Y from their top. */
export const NODE_W = 280;
export const GAP = 120;
export const ROW = 300;
export const PORT_Y = 51;
const COLUMN = NODE_W + GAP;

type Point = { x: number; y: number };
export type FlowNode =
  | { kind: 'trigger'; key: string; x: number; y: number }
  | { kind: 'step'; key: string; x: number; y: number; step: Step; path: StepPath; listPath: StepPath; index: number; last: boolean }
  | { kind: 'add'; key: string; x: number; y: number; listPath: StepPath; side?: 'yes' | 'no' };
export type FlowEdge = { key: string; from: Point; to: Point; delay?: number; insert?: { listPath: StepPath; index: number }; side?: 'yes' | 'no'; dashed?: boolean };

/** How many rows a path needs: a branch at its end stacks its "Sim" rows above its "Não" rows. */
function rows(list: Step[]): number {
  const last = list[list.length - 1];
  return last?.kind === 'branch' ? Math.max(1, rows(last.yes || []) + rows(last.no || [])) : 1;
}

/**
 * Places every card. Each card has an automatic place from the flow's shape, plus the offset the
 * user dragged it by; moving one card leaves the others where they are.
 */
export function layoutFlow(steps: Step[]) {
  const nodes: FlowNode[] = [{ kind: 'trigger', key: 'trigger', x: 0, y: 0 }];
  const edges: FlowEdge[] = [];
  const link = (from: Point, to: Point, extra: Omit<FlowEdge, 'key' | 'from' | 'to'>, key: string) =>
    edges.push({ key, from: { x: from.x + NODE_W, y: from.y + PORT_Y }, to: { x: to.x, y: to.y + PORT_Y }, ...extra });

  function place(list: Step[], listPath: StepPath, parent: Point, x: number, y: number, side?: 'yes' | 'no') {
    if (!list.length) {
      const key = 'add:' + listPath.join('.');
      nodes.push({ kind: 'add', key, x, y, listPath, side });
      link(parent, { x, y }, { side, dashed: true }, key);
      return;
    }
    let previous = parent;
    list.forEach((step, index) => {
      const path = [...listPath, index];
      const auto = { x: x + index * COLUMN, y };
      const at = { x: auto.x + (step.offset?.x || 0), y: auto.y + (step.offset?.y || 0) };
      const key = path.join('.');
      nodes.push({ kind: 'step', key, ...at, step, path, listPath, index, last: index === list.length - 1 });
      link(previous, at, { delay: step.delay_minutes, insert: { listPath, index }, side: index === 0 ? side : undefined }, key);
      if (step.kind === 'branch') {
        const next = auto.x + COLUMN;
        place(step.yes || [], [...path, 'yes'], at, next, auto.y, 'yes');
        place(step.no || [], [...path, 'no'], at, next, auto.y + rows(step.yes || []) * ROW, 'no');
      }
      previous = at;
    });
  }

  place(steps, [], { x: 0, y: 0 }, COLUMN, 0);
  return { nodes, edges };
}

/** A smooth left-to-right curve, and the point halfway along it for the connector's controls. */
export function edgeCurve(from: Point, to: Point) {
  const bend = Math.max(40, Math.abs(to.x - from.x) / 2);
  const c1 = { x: from.x + bend, y: from.y };
  const c2 = { x: to.x - bend, y: to.y };
  return {
    d: `M ${from.x} ${from.y} C ${c1.x} ${c1.y}, ${c2.x} ${c2.y}, ${to.x} ${to.y}`,
    mid: { x: (from.x + 3 * c1.x + 3 * c2.x + to.x) / 8, y: (from.y + 3 * c1.y + 3 * c2.y + to.y) / 8 },
  };
}
