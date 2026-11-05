import type { AgentIdentity } from '../../domain/models';
import type { OfficeRoomConfig, OfficeWorldActorRoute, OfficeWorldPoint } from './types';
import { planOfficeLifePlacements } from './engine/officeLifeEngine';

export interface OfficeWorldNavigation {
  nodes: Map<string, { id: string; x: number; z: number }>;
  adjacency: Map<string, string[]>;
}

export interface OfficeWorldPlan {
  map_revision: string;
  actors: OfficeWorldActorRoute[];
}

function shortestGraphPath(nav: OfficeWorldNavigation, from: string, to: string): string[] | null {
  if (!nav.nodes.has(from) || !nav.nodes.has(to)) return null;
  const queue = [from];
  const previous = new Map<string, string | null>([[from, null]]);
  while (queue.length) {
    const current = queue.shift()!;
    if (current === to) break;
    for (const next of [...(nav.adjacency.get(current) ?? [])].sort()) {
      if (!nav.nodes.has(next) || previous.has(next)) continue;
      previous.set(next, current);
      queue.push(next);
    }
  }
  if (!previous.has(to)) return null;
  const path: string[] = [];
  for (let current: string | null = to; current; current = previous.get(current) ?? null) path.push(current);
  return path.reverse();
}

export function buildOfficeAgentWalkingCircuit(
  placement: { unitId: string; waypoints: ReadonlyArray<{ x: number; z: number }> },
  nav: OfficeWorldNavigation,
): OfficeWorldPoint[] | null {
  const corridorPath = shortestGraphPath(nav, `aisle-${placement.unitId}`, 'main-entry');
  const seat = placement.waypoints[0];
  if (!corridorPath || !seat) return null;
  const graphPoints = corridorPath.map((id) => nav.nodes.get(id)!).map(({ x, z }) => ({ x, z }));
  // The graph path exits the neighborhood via its aisle, doorway and corridor.
  // Return along the same traversable path, ending at the aisle before the
  // implicit short segment back to the chair. Omit duplicate/near-duplicate
  // waypoints to satisfy the backend route contract.
  const points = [seat, ...graphPoints, ...graphPoints.slice(0, -1).reverse()];
  return points.filter((point, index) => index === 0
    || Math.hypot(point.x - points[index - 1].x, point.z - points[index - 1].z) >= 0.1);
}

export function resolveLocalNpcPositions(plan: OfficeWorldPlan, nowMs = Date.now()) {
  return plan.actors.filter((actor) => actor.actor_kind === 'NPC').map((actor) => {
    const points = actor.route;
    const lengths = points.map((point, index) => {
      const next = points[(index + 1) % points.length];
      return Math.hypot(next.x - point.x, next.z - point.z);
    });
    const perimeter = lengths.reduce((sum, length) => sum + length, 0);
    let remaining = ((nowMs / 1000) * actor.speed) % perimeter;
    let position = points[0];
    let facing = 0;
    for (let index = 0; index < points.length; index += 1) {
      const start = points[index];
      const end = points[(index + 1) % points.length];
      const length = lengths[index];
      if (remaining <= length) {
        const ratio = length ? remaining / length : 0;
        position = { x: start.x + (end.x - start.x) * ratio, z: start.z + (end.z - start.z) * ratio };
        facing = Math.atan2(end.x - start.x, end.z - start.z);
        break;
      }
      remaining -= length;
    }
    return { actor_id: actor.actor_id, actor_kind: 'NPC' as const, map_revision: plan.map_revision,
      x: position.x, z: position.z, facing, simulation_only: true as const };
  });
}

function stableRevision(value: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return `office-map-v1-${(hash >>> 0).toString(16).padStart(8, '0')}`;
}

function pathFromEntry(nav: OfficeWorldNavigation): OfficeWorldPoint[][] {
  const entry = nav.nodes.get('main-entry');
  if (!entry) return [];
  const queue = [entry.id];
  const previous = new Map<string, string | null>([[entry.id, null]]);
  while (queue.length) {
    const current = queue.shift()!;
    for (const next of [...(nav.adjacency.get(current) ?? [])].sort()) {
      if (previous.has(next) || !nav.nodes.has(next)) continue;
      previous.set(next, current);
      queue.push(next);
    }
  }
  const leaves = [...previous.keys()].filter((id) => id !== entry.id)
    .sort((a, b) => (previous.get(b) === entry.id ? 1 : 0) - (previous.get(a) === entry.id ? 1 : 0)
      || a.localeCompare(b));
  const routes: OfficeWorldPoint[][] = [];
  for (const target of leaves) {
    const ids: string[] = [];
    let cursor: string | null = target;
    while (cursor) { ids.push(cursor); cursor = previous.get(cursor) ?? null; }
    ids.reverse();
    if (ids.length < 2) continue;
    // Walk out through the actual corridor graph and return on the same graph.
    const loop = [...ids, ...ids.slice(1, -1).reverse()];
    const route = loop.map((id) => nav.nodes.get(id)!).filter((point, index, all) =>
      index === 0 || Math.hypot(point.x - all[index - 1].x, point.z - all[index - 1].z) >= 0.1
    ).map(({ x, z }) => ({ x, z }));
    if (route.length >= 2) routes.push(route);
  }
  return routes.length ? routes : [[
    { x: entry.x - 1, z: entry.z },
    { x: entry.x, z: entry.z + 1 },
    { x: entry.x + 1, z: entry.z },
  ]];
}

export function buildOfficeWorldPlan(input: {
  agents: readonly AgentIdentity[];
  rooms: readonly OfficeRoomConfig[];
  navigation: OfficeWorldNavigation;
  nowMs?: number;
}): OfficeWorldPlan {
  const placements = planOfficeLifePlacements(input.agents, input.rooms, {
    isDemo: false, nowMs: input.nowMs, ambientWalkEnabled: true,
  });
  const agents = [...placements.values()]
    .filter((placement) => placement.activity.kind === 'WALKING'
      && placement.activity.provenance === 'AMBIENT_ANIMATION'
      && placement.unitId !== 'unit-unassigned')
    .sort((a, b) => a.agentId.localeCompare(b.agentId))
    .map((placement): OfficeWorldActorRoute | null => {
      const route = buildOfficeAgentWalkingCircuit(placement, input.navigation);
      if (!route || route.length < 2) return null;
      return {
      actor_id: placement.agentId,
      actor_kind: 'AGENT',
      route,
      speed: 0.52,
      };
    }).filter((actor): actor is OfficeWorldActorRoute => actor !== null);
  const paths = pathFromEntry(input.navigation);
  const npcCandidates: Array<[string, number]> = [
    ['npc:receptionist', 0], ['npc:copy-room', Math.min(1, paths.length - 1)],
    ['npc:office-runner', Math.min(2, paths.length - 1)],
  ];
  const npcs: OfficeWorldActorRoute[] = npcCandidates.filter(([, index]) => index >= 0).map(([actorId, index]) => ({
    actor_id: actorId as string,
    actor_kind: 'NPC',
    route: paths[index as number],
    speed: actorId === 'npc:receptionist' ? 0.16 : 0.34,
  }));
  const actors = [...agents, ...npcs];
  const planGeometry = JSON.stringify({
    rooms: input.rooms.map(({ id, x, z, width, depth }) => [id, x, z, width, depth]).sort(),
    actors: actors.map(({ actor_id, actor_kind, route, speed }) => [actor_id, actor_kind, route, speed]),
  });
  return { map_revision: stableRevision(planGeometry), actors };
}
