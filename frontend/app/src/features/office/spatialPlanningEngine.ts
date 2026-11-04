import type { OfficeRoomConfig } from './types';

export interface OfficeZoneRequest {
  id: string;
  parentId: string | null;
  width: number;
  depth: number;
}

export interface PlannedOfficeZone {
  id: string;
  x: number;
  z: number;
  width: number;
  depth: number;
}

export interface WorkNeighborhoodDeskPlacement {
  slotIndex: number;
  x: number;
  z: number;
}

/**
 * Stable sequential circle packing for one desk per observed agent. A prefix
 * never moves when the department grows; each next desk is placed in the
 * lowest-cost free gap around the existing neighborhood rather than on a
 * fixed grid. Spacing is minimum center distance, not a site-wide pitch.
 */
export function planWorkNeighborhoodDesks(
  count: number,
  rotationSeed = 'office',
): WorkNeighborhoodDeskPlacement[] {
  const safeCount = Math.max(0, Math.floor(count));
  const spacing = 1.48;
  let hash = 2166136261;
  for (const char of rotationSeed) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  const rotation = ((hash >>> 0) / 0xffffffff) * Math.PI * 2;
  const placements: WorkNeighborhoodDeskPlacement[] = [];
  for (let slotIndex = 0; slotIndex < safeCount; slotIndex += 1) {
    if (slotIndex === 0) {
      placements.push({ slotIndex, x: 0, z: 0 });
      continue;
    }
    const candidates = new Map<string, { x: number; z: number; cost: number }>();
    const phase = rotation + slotIndex * Math.PI * (3 - Math.sqrt(5));
    for (const anchor of placements) {
      for (let ray = 0; ray < 32; ray += 1) {
        const angle = phase + ray * (Math.PI * 2 / 32);
        const x = Number((anchor.x + Math.cos(angle) * spacing).toFixed(4));
        const z = Number((anchor.z + Math.sin(angle) * spacing).toFixed(4));
        if (placements.some((placed) => Math.hypot(x - placed.x, z - placed.z) < spacing - 0.005)) continue;
        const xs = [...placements.map((placed) => placed.x), x];
        const zs = [...placements.map((placed) => placed.z), z];
        const spanX = Math.max(...xs) - Math.min(...xs);
        const spanZ = Math.max(...zs) - Math.min(...zs);
        const centroidDistance = Math.hypot(
          x - xs.reduce((sum, value) => sum + value, 0) / xs.length,
          z - zs.reduce((sum, value) => sum + value, 0) / zs.length,
        );
        const key = `${x},${z}`;
        const shapePenalty = Math.abs(spanX - spanZ) * 4;
        candidates.set(key, { x, z, cost: spanX * spanZ + shapePenalty + (spanX + spanZ) * 0.18 + centroidDistance * 0.08 });
      }
    }
    const chosen = [...candidates.values()].sort((a, b) => a.cost - b.cost || a.x - b.x || a.z - b.z)[0];
    if (!chosen) throw new Error(`Unable to pack desk ${slotIndex} in work neighborhood`);
    placements.push({ slotIndex, x: chosen.x, z: chosen.z });
  }
  return placements;
}

// A continuous aisle, not a department-to-department grid pitch. The zone
// contract is retained for consumers during migration to desk-level planning.
// 1.35m circulation width plus a 0.4m service/avoidance margin.
export const WORK_NEIGHBORHOOD_CLEARANCE_METERS = 2.15;
const CLEARANCE = WORK_NEIGHBORHOOD_CLEARANCE_METERS;
const DIRECTIONS = [
  [1, 0], [0, 1], [-1, 0], [0, -1],
  [0.7071, 0.7071], [-0.7071, 0.7071], [-0.7071, -0.7071], [0.7071, -0.7071],
] as const;

function stableHash(value: string): number {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function overlaps(request: OfficeZoneRequest, point: { x: number; z: number }, placed: PlannedOfficeZone): boolean {
  return Math.abs(point.x - placed.x) < (request.width + placed.width) / 2 + CLEARANCE &&
    Math.abs(point.z - placed.z) < (request.depth + placed.depth) / 2 + CLEARANCE;
}

function envelopeArea(zones: readonly PlannedOfficeZone[], request: OfficeZoneRequest, point: { x: number; z: number }): number {
  const xs = zones.flatMap((zone) => [zone.x - zone.width / 2, zone.x + zone.width / 2]);
  const zs = zones.flatMap((zone) => [zone.z - zone.depth / 2, zone.z + zone.depth / 2]);
  xs.push(point.x - request.width / 2, point.x + request.width / 2);
  zs.push(point.z - request.depth / 2, point.z + request.depth / 2);
  return (Math.max(...xs) - Math.min(...xs)) * (Math.max(...zs) - Math.min(...zs));
}

function* adjacentCandidates(request: OfficeZoneRequest, placed: readonly PlannedOfficeZone[]): Generator<{ x: number; z: number }> {
  for (const neighbor of placed) {
    for (let directionIndex = 0; directionIndex < DIRECTIONS.length; directionIndex += 1) {
      const [dx, dz] = DIRECTIONS[directionIndex];
      const supportNew = (request.width * Math.abs(dx) + request.depth * Math.abs(dz)) / 2;
      const supportNeighbor = (neighbor.width * Math.abs(dx) + neighbor.depth * Math.abs(dz)) / 2;
      // Tiny keyed tangent offsets create an articulated neighborhood while
      // preserving the hard axis-aligned clearance test below.
      const tangent = ((stableHash(`${request.id}:${neighbor.id}:${directionIndex}`) % 1001) / 1000 - 0.5) * 0.8;
      yield {
        x: neighbor.x + dx * (supportNew + supportNeighbor + CLEARANCE) - dz * tangent,
        z: neighbor.z + dz * (supportNew + supportNeighbor + CLEARANCE) + dx * tangent,
      };
    }
  }
}

function candidateCost(
  request: OfficeZoneRequest,
  point: { x: number; z: number },
  placed: readonly PlannedOfficeZone[],
  parent?: PlannedOfficeZone,
): number {
  const area = envelopeArea(placed, request, point);
  const minX = Math.min(...placed.map((zone) => zone.x - zone.width / 2), point.x - request.width / 2);
  const maxX = Math.max(...placed.map((zone) => zone.x + zone.width / 2), point.x + request.width / 2);
  const minZ = Math.min(...placed.map((zone) => zone.z - zone.depth / 2), point.z - request.depth / 2);
  const maxZ = Math.max(...placed.map((zone) => zone.z + zone.depth / 2), point.z + request.depth / 2);
  const parentDistance = parent ? Math.hypot(point.x - parent.x, point.z - parent.z) : 0;
  const centroidX = (minX + maxX) / 2;
  const centroidZ = (minZ + maxZ) / 2;
  const spanX = maxX - minX;
  const spanZ = maxZ - minZ;
  const shapePenalty = Math.abs(spanX - spanZ) * 16;
  // Prefer a compact, slightly articulated envelope and keep children close
  // to their parent; stable IDs break exact ties reproducibly.
  return area + (spanX + spanZ) * 0.4 + shapePenalty + parentDistance * (parent ? 1.5 : 0) +
    Math.hypot(point.x - centroidX, point.z - centroidZ) * 0.08;
}

/** Deterministic compact neighborhood placement. Existing valid positions win. */
export function planOfficeZones(
  requests: readonly OfficeZoneRequest[],
  previous: readonly Pick<OfficeRoomConfig, 'id' | 'x' | 'z' | 'width' | 'depth'>[] = [],
): PlannedOfficeZone[] {
  const byId = new Map(requests.map((request) => [request.id, request]));
  const previousById = new Map(previous.map((zone) => [zone.id, zone]));
  const depthOf = (request: OfficeZoneRequest): number => {
    let depth = 0;
    let parentId = request.parentId;
    const seen = new Set([request.id]);
    while (parentId && byId.has(parentId) && !seen.has(parentId)) {
      seen.add(parentId);
      parentId = byId.get(parentId)!.parentId;
      depth += 1;
    }
    return depth;
  };
  const ordered = [...requests].sort((a, b) => depthOf(a) - depthOf(b) || a.id.localeCompare(b.id));
  const planned: PlannedOfficeZone[] = [];
  const pending = new Set(ordered.map((request) => request.id));

  for (const request of ordered) {
    const prior = previousById.get(request.id);
    if (!prior || planned.some((zone) => overlaps(request, prior, zone))) continue;
    planned.push({ ...request, x: prior.x, z: prior.z });
    pending.delete(request.id);
  }

  for (const request of ordered) {
    if (!pending.has(request.id)) continue;
    const parent = planned.find((zone) => zone.id === request.parentId);
    if (planned.length === 0) {
      planned.push({ ...request, x: 0, z: 0 });
      continue;
    }
    const parentCandidates = parent ? [...adjacentCandidates(request, [parent])] : [];
    const candidates = parentCandidates.length > 0 &&
      parentCandidates.some((point) => !planned.some((zone) => overlaps(request, point, zone)))
      ? parentCandidates
      : [...adjacentCandidates(request, planned)];
    // If preserved placements leave no local opening, grow from the occupied
    // envelope rather than restarting the layout on a fixed world lattice.
    if (candidates.length === 0) candidates.push({ x: 0, z: 0 });
    const valid = candidates.filter((point) => !planned.some((zone) => overlaps(request, point, zone)));
    const chosen = valid.sort((a, b) => candidateCost(request, a, planned, parent) - candidateCost(request, b, planned, parent) ||
      stableHash(`${request.id}:${a.x}:${a.z}`) - stableHash(`${request.id}:${b.x}:${b.z}`))[0];
    if (!chosen) throw new Error(`Unable to place organizational zone ${request.id}`);
    planned.push({ ...request, ...chosen });
    pending.delete(request.id);
  }
  return planned.sort((a, b) => a.id.localeCompare(b.id));
}
