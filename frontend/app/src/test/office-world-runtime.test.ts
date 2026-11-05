import { describe, expect, it } from 'vitest';
import { isAssignmentLeaseValid } from '../features/office/engine/officeLifeEngine';
import type { AgentIdentity } from '../domain/models';
import { buildOfficeAgentWalkingCircuit, buildOfficeWorldPlan, resolveLocalNpcPositions } from '../features/office/officeWorldRuntime';

const assignment = (leaseExpiresAt: string | null): AgentIdentity['currentAssignments'][number] => ({
  id: 'assignment-1', projectId: 'project-1', projectName: 'Project', taskId: 'task-1',
  taskTitle: 'Task', assignedAt: '2026-01-01T00:00:00.000Z', leaseExpiresAt, status: 'ACTIVE',
});

describe('office runtime lease evidence', () => {
  it('fails closed when an expiry exists but cannot be parsed', () => {
    expect(isAssignmentLeaseValid(assignment('not-a-date'), Date.parse('2026-01-01T00:00:00Z')))
      .toEqual({ valid: false, expired: false });
  });

  it('treats an expiry equal to now as expired and a future expiry as valid', () => {
    const now = Date.parse('2026-01-01T00:00:00Z');
    expect(isAssignmentLeaseValid(assignment('2026-01-01T00:00:00Z'), now))
      .toEqual({ valid: false, expired: true });
    expect(isAssignmentLeaseValid(assignment('2026-01-01T00:00:01Z'), now))
      .toEqual({ valid: true, expired: false });
  });
});

describe('office ambient world plan', () => {
  it('routes idle-agent circuits through the neighborhood aisle and connected corridor graph', () => {
    const navigation = {
      nodes: new Map([
        ['aisle-unit-a', { id: 'aisle-unit-a', x: 0, z: 1 }],
        ['doorway-unit-a', { id: 'doorway-unit-a', x: 0, z: 2 }],
        ['main-entry', { id: 'main-entry', x: 0, z: 3 }],
      ]),
      adjacency: new Map([
        ['aisle-unit-a', ['doorway-unit-a']], ['doorway-unit-a', ['aisle-unit-a', 'main-entry']],
        ['main-entry', ['doorway-unit-a']],
      ]),
    };
    const route = buildOfficeAgentWalkingCircuit({ unitId: 'unit-a', waypoints: [{ x: 1, z: 1 }] }, navigation);
    expect(route).toEqual([
      { x: 1, z: 1 }, { x: 0, z: 1 }, { x: 0, z: 2 }, { x: 0, z: 3 }, { x: 0, z: 2 }, { x: 0, z: 1 },
    ]);
  });

  it('creates deterministic visual-only NPC routes without fabricating agent actors', () => {
    const navigation = {
      nodes: new Map([
        ['main-entry', { id: 'main-entry', x: 0, z: 0 }],
        ['corridor-a', { id: 'corridor-a', x: 0, z: 5 }],
        ['corridor-b', { id: 'corridor-b', x: 4, z: 5 }],
      ]),
      adjacency: new Map([
        ['main-entry', ['corridor-a']], ['corridor-a', ['main-entry', 'corridor-b']],
        ['corridor-b', ['corridor-a']],
      ]),
    };
    const input = { agents: [], rooms: [], navigation };
    const plan = buildOfficeWorldPlan(input);
    expect(plan).toEqual(buildOfficeWorldPlan(input));
    expect(plan.actors.map(({ actor_id }) => actor_id)).toEqual([
      'npc:receptionist', 'npc:copy-room', 'npc:office-runner',
    ]);
    expect(plan.actors.every(({ actor_kind }) => actor_kind === 'NPC')).toBe(true);
    expect(resolveLocalNpcPositions(plan, 1000)).toHaveLength(3);
    expect(resolveLocalNpcPositions(plan, 2000)[0]).not.toEqual(resolveLocalNpcPositions(plan, 1000)[0]);
  });
});
