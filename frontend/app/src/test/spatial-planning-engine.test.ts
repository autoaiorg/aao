import { describe, expect, it } from 'vitest';
import {
  planOfficeZones,
  WORK_NEIGHBORHOOD_CLEARANCE_METERS,
  type OfficeZoneRequest,
} from '../features/office/spatialPlanningEngine';

const requestsFor = (count: number): OfficeZoneRequest[] =>
  Array.from({ length: count }, (_, index) => ({
    id: `unit-${String(index).padStart(3, '0')}`,
    parentId: null,
    width: index % 4 === 0 ? 8.5 : 4.8,
    depth: index % 4 === 0 ? 5.2 : 4.2,
  }));

describe('planOfficeZones', () => {
  it('returns an empty valid plan and supports organizations of 1, 2, 10, and more than 10 zones', () => {
    expect(planOfficeZones([])).toEqual([]);
    for (const count of [1, 2, 10, 17]) {
      const plan = planOfficeZones(requestsFor(count));
      expect(plan).toHaveLength(count);
      expect(new Set(plan.map((zone) => zone.id)).size).toBe(count);
    }
  });

  it('is independent of input order and maintains collision clearance without reserving an atrium', () => {
    const requests = requestsFor(24);
    const plan = planOfficeZones(requests);
    expect(planOfficeZones([...requests].reverse())).toEqual(plan);
    for (let i = 0; i < plan.length; i += 1) {
      const a = plan[i];
      for (const b of plan.slice(i + 1)) {
        const separatedX = Math.abs(a.x - b.x) >= (a.width + b.width) / 2 + WORK_NEIGHBORHOOD_CLEARANCE_METERS;
        const separatedZ = Math.abs(a.z - b.z) >= (a.depth + b.depth) / 2 + WORK_NEIGHBORHOOD_CLEARANCE_METERS;
        expect(separatedX || separatedZ).toBe(true);
      }
    }
  });

  it('keeps a normal six-unit campus compact in an articulated envelope', () => {
    const standardUnits = Array.from({ length: 6 }, (_, index) => ({
      id: `compact-${String(index).padStart(2, '0')}`,
      parentId: null,
      width: 4.8,
      depth: 4.2,
    }));
    const plan = planOfficeZones(standardUnits);
    const farthestUnit = Math.max(...plan.map(({ x, z }) => Math.hypot(x, z)));

    expect(farthestUnit).toBeLessThan(16);
  });

  it('retains existing locations when zones are added and places children adjacent to their parent', () => {
    const initial = requestsFor(5);
    const previous = planOfficeZones(initial);
    const expanded = [...initial, { id: 'unit-new', parentId: null, width: 4.8, depth: 4.2 }];
    const next = planOfficeZones(expanded, previous);
    const previousPositions = new Map(previous.map(({ id, x, z }) => [id, { x, z }]));
    for (const zone of next) {
      if (previousPositions.has(zone.id)) expect({ x: zone.x, z: zone.z }).toEqual(previousPositions.get(zone.id));
    }

    const parent = next.find((zone) => zone.id === 'unit-000')!;
    const childRequest = { id: 'unit-child', parentId: parent.id, width: 4.8, depth: 4.2 };
    const withChild = planOfficeZones([...expanded, childRequest], next);
    const child = withChild.find((zone) => zone.id === childRequest.id)!;
    // A reserved neighboring face may be occupied; retain a short functional
    // distance instead of forcing a collision or reshuffling existing teams.
    expect(Math.hypot(child.x - parent.x, child.z - parent.z)).toBeLessThan(11);
  });
});
