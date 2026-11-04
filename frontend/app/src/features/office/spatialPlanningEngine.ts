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

const CLEARANCE = 1.5;
const ATRIUM_RADIUS = 3.75;
// A 9 x 7 metre planning grid keeps regular teams connected to the atrium
// without creating the oversized empty plazas produced by the earlier
// 12 x 8 spacing. The overlap check still accounts for actual zone dimensions.
// Density is based on common department footprints plus a usable aisle. These
// are planning hints, not a global workstation lattice: parent-adjacent and
// persisted placements still take precedence.
const GRID_X = 8;
const GRID_Z = 6.5;

function stableHash(value: string): number {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function overlaps(a: OfficeZoneRequest, point: { x: number; z: number }, b: PlannedOfficeZone): boolean {
  return (
    Math.abs(point.x - b.x) < (a.width + b.width) / 2 + CLEARANCE &&
    Math.abs(point.z - b.z) < (a.depth + b.depth) / 2 + CLEARANCE
  );
}

function intersectsAtrium(request: OfficeZoneRequest, point: { x: number; z: number }): boolean {
  const dx = Math.max(Math.abs(point.x) - request.width / 2, 0);
  const dz = Math.max(Math.abs(point.z) - request.depth / 2, 0);
  return dx * dx + dz * dz < ATRIUM_RADIUS * ATRIUM_RADIUS;
}

function* candidatesFor(request: OfficeZoneRequest, parent: PlannedOfficeZone | undefined): Generator<{ x: number; z: number }> {
  if (parent) {
    const horizontal = (parent.width + request.width) / 2 + CLEARANCE + 1;
    const vertical = (parent.depth + request.depth) / 2 + CLEARANCE + 1;
    yield* [
      { x: parent.x + horizontal, z: parent.z },
      { x: parent.x - horizontal, z: parent.z },
      { x: parent.x, z: parent.z - vertical },
      { x: parent.x, z: parent.z + vertical },
    ];
  }

  // The keyed rotation breaks ties consistently without sorting large candidate sets.
  for (let radius = 1; radius <= 100; radius += 1) {
    const perimeter: Array<[number, number]> = [];
    for (let x = -radius; x <= radius; x += 1) {
      perimeter.push([x, -radius], [x, radius]);
    }
    for (let z = -radius + 1; z < radius; z += 1) {
      perimeter.push([-radius, z], [radius, z]);
    }
    const offset = stableHash(request.id) % perimeter.length;
    for (let index = 0; index < perimeter.length; index += 1) {
      const [gx, gz] = perimeter[(index + offset) % perimeter.length];
      yield { x: gx * GRID_X, z: gz * GRID_Z };
    }
  }
}

/** Pure architectural zone planner. Prior locations are retained when they remain valid. */
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

  // Preserve valid persisted positions first, so routine structure updates do not reshuffle existing zones.
  for (const request of ordered) {
    const prior = previousById.get(request.id);
    if (!prior) continue;
    const point = { x: prior.x, z: prior.z };
    if (intersectsAtrium(request, point) || planned.some((zone) => overlaps(request, point, zone))) continue;
    planned.push({ ...request, ...point });
    pending.delete(request.id);
  }

  for (const request of ordered) {
    if (!pending.has(request.id)) continue;
    const parent = planned.find((zone) => zone.id === request.parentId);
    let candidate: { x: number; z: number } | undefined;
    for (const point of candidatesFor(request, parent)) {
      if (!intersectsAtrium(request, point) && !planned.some((zone) => overlaps(request, point, zone))) {
        candidate = point;
        break;
      }
    }
    if (!candidate) throw new Error(`Unable to place organizational zone ${request.id}`);
    planned.push({ ...request, ...candidate });
    pending.delete(request.id);
  }
  return planned.sort((a, b) => a.id.localeCompare(b.id));
}
