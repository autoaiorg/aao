import type { OrgUnit } from '../../domain/models';
import type { OfficeRoomConfig } from './types';

const UNIT_COLORS = [
  ['#1e3a8a', '#3b82f6'],
  ['#4c1d95', '#8b5cf6'],
  ['#064e3b', '#10b981'],
  ['#78350f', '#f59e0b'],
  ['#164e63', '#06b6d4'],
  ['#713f12', '#d97706'],
] as const;

/** Build a display-only layout from persisted organization units; it creates no organization data. */
export function buildLiveOfficeRooms(units: OrgUnit[]): OfficeRoomConfig[] {
  const byId = new Map(units.map((unit) => [unit.id, unit]));
  const hierarchyDepth = (unit: OrgUnit): number => {
    let current = unit;
    let depth = 0;
    const visited = new Set([unit.id]);
    while (current.parentId) {
      const parent = byId.get(current.parentId);
      if (!parent || visited.has(parent.id)) break;
      visited.add(parent.id);
      current = parent;
      depth += 1;
    }
    return depth;
  };
  const orderedUnits = [...units].sort((left, right) => {
    const depth = hierarchyDepth(left) - hierarchyDepth(right);
    if (depth !== 0) return depth;
    const parent = (left.parentId ?? '').localeCompare(right.parentId ?? '');
    if (parent !== 0) return parent;
    const code = left.code.localeCompare(right.code);
    return code !== 0 ? code : left.id.localeCompare(right.id);
  });
  const levelCounts = new Map<number, number>();
  orderedUnits.forEach((unit) => {
    const depth = hierarchyDepth(unit);
    levelCounts.set(depth, (levelCounts.get(depth) ?? 0) + 1);
  });
  const maxDepth = Math.max(0, ...levelCounts.keys());
  const levelPositions = new Map<number, number>();
  return orderedUnits.map((unit, index) => {
    const depth = hierarchyDepth(unit);
    const count = levelCounts.get(depth) ?? 1;
    const position = levelPositions.get(depth) ?? 0;
    levelPositions.set(depth, position + 1);
    const [color, accentColor] = UNIT_COLORS[index % UNIT_COLORS.length];
    return {
      id: unit.id,
      code: unit.code,
      name: unit.name,
      x: (position - (count - 1) / 2) * 6,
      z: (depth - maxDepth / 2) * 6,
      width: 4.8,
      depth: 4.2,
      color,
      accentColor,
    };
  });
}
