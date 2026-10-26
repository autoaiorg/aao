import { describe, expect, it } from 'vitest';
import type { OrgUnit } from '../domain/models';
import { buildLiveOfficeRooms } from '../features/office/liveOfficeLayout';

const unit = (id: string, code: string, name = code, parentId: string | null = null): OrgUnit => ({
  id,
  code,
  name,
  parentId,
  leadRole: 'unknown',
  leadAgentId: null,
  description: '',
  standingCount: 0,
  ephemeralCount: 0,
  activeProjectsCount: 0,
});

describe('buildLiveOfficeRooms', () => {
  it('maps actual unit IDs and labels to a deterministic display layout', () => {
    const units = [unit('unit-z', 'Z', 'Zulu'), unit('unit-a', 'A', 'Alpha')];
    const rooms = buildLiveOfficeRooms(units);

    expect(rooms.map(({ id, code, name }) => ({ id, code, name }))).toEqual([
      { id: 'unit-a', code: 'A', name: 'Alpha' },
      { id: 'unit-z', code: 'Z', name: 'Zulu' },
    ]);
    expect(rooms[0].x).toBe(-3);
    expect(rooms[1].x).toBe(3);
    expect(buildLiveOfficeRooms(units)).toEqual(rooms);
  });

  it('returns no synthetic units when live organization is empty', () => {
    expect(buildLiveOfficeRooms([])).toEqual([]);
  });

  it('does not replace unknown persisted IDs with the demo roster IDs', () => {
    const [room] = buildLiveOfficeRooms([unit('org-division-17', 'D17', 'Research')]);
    expect(room.id).toBe('org-division-17');
    expect(room.id).not.toBe('unit-eng');
  });

  it('places persisted child units on a deeper organizational level', () => {
    const [root, child, grandchild] = buildLiveOfficeRooms([
      unit('child', 'CHILD', 'Child', 'root'),
      unit('root', 'ROOT'),
      unit('grandchild', 'GRANDCHILD', 'Grandchild', 'child'),
    ]);

    expect(root.id).toBe('root');
    expect(child.id).toBe('child');
    expect(grandchild.id).toBe('grandchild');
    expect(root.z).toBeLessThan(child.z);
    expect(child.z).toBeLessThan(grandchild.z);
  });
});
