import { describe, expect, it } from 'vitest';
import type { AgentIdentity, OrgUnit } from '../domain/models';
import {
  buildCampusNavGraph,
  buildCorporateCampusLayout,
  buildLiveOfficeRooms,
  computeArchitecturalOutline,
  resolveLiveOrganizationAttribution,
  selectOfficeZoneKind,
} from '../features/office/liveOfficeLayout';
import { buildDepartmentInteriorLayout, planOfficeLifePlacements } from '../features/office/engine/officeLifeEngine';
import {
  planWorkNeighborhoodDesks,
  planOfficeZones,
  WORK_NEIGHBORHOOD_CLEARANCE_METERS,
} from '../features/office/spatialPlanningEngine';

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

describe('capacity-aware spatial layout', () => {
  it('packs exactly one stable, separated desk per assigned agent in an organic neighborhood', () => {
    const one = planWorkNeighborhoodDesks(1, 'unit-eng');
    const three = planWorkNeighborhoodDesks(3, 'unit-eng');
    const eight = planWorkNeighborhoodDesks(8, 'unit-eng');
    expect(one).toHaveLength(1);
    expect(three).toHaveLength(3);
    expect(eight).toHaveLength(8);
    expect(eight.slice(0, 3)).toEqual(three);
    expect(planWorkNeighborhoodDesks(8, 'unit-eng')).toEqual(eight);
    expect(new Set(eight.map(({ x }) => x)).size).toBeGreaterThan(4);
    expect(new Set(eight.map(({ z }) => z)).size).toBeGreaterThan(4);
    for (let left = 0; left < eight.length; left += 1) {
      for (let right = left + 1; right < eight.length; right += 1) {
        expect(Math.hypot(eight[left].x - eight[right].x, eight[left].z - eight[right].z)).toBeGreaterThanOrEqual(1.35);
      }
    }
  });

  it('does not turn a disabled historical identity into a department desk occupant', () => {
    const department = unit('unit-eng', 'ENG', 'Ingeniería');
    const historical = makeAgent({ id: 'agent-historical', unitId: department.id, credentialStatus: 'DISABLED' });
    const layout = buildCorporateCampusLayout([department], [historical], { isDemo: false });
    const departmentRoom = layout.rooms.find((room) => room.id === department.id)!;
    const holdingRoom = layout.rooms.find((room) => room.id === 'unit-unassigned');
    expect(departmentRoom.workstationCapacity).toBe(0);
    expect(holdingRoom).toBeDefined();

    const placements = planOfficeLifePlacements(layout.normalizedAgents, layout.rooms, {
      isDemo: false,
      ambientWalkEnabled: false,
    });
    expect(placements.get(historical.id)?.activity.kind).toBe('DISCONNECTED');
    expect(placements.get(historical.id)?.isSeated).toBe(false);
  });

  it('selects architectural modules from declared nature rather than unit IDs or hierarchy', () => {
    const layout = buildCorporateCampusLayout([
      unit('unit-audit', 'AUDIT', 'Equipo de Investigación'),
      unit('org-42', 'ORG', 'Auditoría Independiente y Verificación'),
    ], [], { isDemo: false });
    expect(layout.rooms.find((room) => room.id === 'unit-audit')?.kind).toBe('canonical-department');
    expect(layout.rooms.find((room) => room.id === 'org-42')?.kind).toBe('audit-enclave');
    expect(selectOfficeZoneKind({ name: 'Dirección Ejecutiva', description: '', leadRole: '' })).toBe('executive-suite');
  });

  it('places the navigation entry at the rendered envelope facade opening', () => {
    const rooms = buildCorporateCampusLayout([
      unit('unit-a', 'A'), unit('unit-b', 'B'), unit('unit-c', 'C'),
    ], []).rooms;
    const outline = computeArchitecturalOutline(rooms);
    const edge = [...outline].map((start, index) => ({ start, end: outline[(index + 1) % outline.length] }))
      .sort((a, b) => ((b.start.z + b.end.z) / 2) - ((a.start.z + a.end.z) / 2))[0];
    const dx = edge.end.x - edge.start.x;
    const dz = edge.end.z - edge.start.z;
    const length = Math.hypot(dx, dz);
    const entry = buildCampusNavGraph(rooms).nodes.get('main-entry')!;

    expect(entry.x).toBeCloseTo((edge.start.x + edge.end.x) / 2 + dz / length * 2.4);
    expect(entry.z).toBeCloseTo((edge.start.z + edge.end.z) / 2 - dx / length * 2.4);
  });

  it('does not materialize desks from declared headcount without assigned identities', () => {
    const planned = { ...unit('unit-planned', 'PLAN'), standingCount: 12, ephemeralCount: 3 };
    const { rooms, normalizedAgents } = buildCorporateCampusLayout([planned], [], { isDemo: false });
    const room = rooms.find(({ id }) => id === planned.id)!;

    expect(room.workstationCapacity).toBe(0);
    expect(normalizedAgents).toEqual([]);
    expect(buildDepartmentInteriorLayout(room).workstations).toHaveLength(0);
  });

  it.each([1, 3, 8])('renders exactly one desk for each of %i assigned agents', (count) => {
    const team = unit('assigned-team', 'TEAM');
    const agents = Array.from({ length: count }, (_, index) => makeAgent({ id: `agent-${index}`, unitId: team.id, credentialStatus: 'ENABLED' }));
    const room = buildCorporateCampusLayout([team], agents).rooms.find(({ id }) => id === team.id)!;

    expect(room.workstationCapacity).toBe(count);
    const desks = buildDepartmentInteriorLayout(room).workstations;
    expect(desks).toHaveLength(count);
    expect(new Set(desks.map(({ deskWorldX, deskWorldZ }) => `${deskWorldX}:${deskWorldZ}`)).size).toBe(count);
    if (count === 1) {
      expect(desks[0].deskLocalX).toBe(0);
      expect(room.width).toBeLessThan(4);
      expect(room.depth).toBeLessThan(4);
    }
    if (count === 8) {
      expect(room.width).toBeLessThan(9);
      expect(room.depth).toBeLessThan(10);
    }
  });

  it('excludes historical and unassigned identities from departmental desk counts', () => {
    const team = unit('assigned-team', 'TEAM');
    const agents = [
      makeAgent({ id: 'active', unitId: team.id, credentialStatus: 'ENABLED' }),
      makeAgent({ id: 'active-2', unitId: team.id, credentialStatus: 'ENABLED' }),
      makeAgent({ id: 'historical', unitId: team.id, credentialStatus: 'DISABLED' }),
      makeAgent({ id: 'unassigned', unitId: 'unit-unassigned' }),
    ];
    const layout = buildCorporateCampusLayout([team], agents);
    const room = layout.rooms.find(({ id }) => id === team.id)!;
    const holding = layout.rooms.find(({ id }) => id === 'unit-unassigned')!;

    expect(buildDepartmentInteriorLayout(room).workstations).toHaveLength(2);
    expect(buildDepartmentInteriorLayout(holding).workstations).toHaveLength(0);
  });

  it('fits workstation geometry inside expanded departments for teams over ten', () => {
    const team = unit('unit-large-team', 'LARGE', 'Large team');
    const agents = Array.from({ length: 25 }, (_, index) =>
      makeAgent({ id: `large-agent-${index}`, unitId: team.id, credentialStatus: 'ENABLED' })
    );
    const room = buildCorporateCampusLayout([team], agents).rooms.find(({ id }) => id === team.id)!;
    const interior = buildDepartmentInteriorLayout(room);

    expect(room.workstationCapacity).toBe(agents.length);
    expect(interior.workstations).toHaveLength(room.workstationCapacity!);
    for (const slot of interior.workstations) {
      expect(Math.abs(slot.deskLocalX) + 0.5).toBeLessThanOrEqual(room.width / 2);
      expect(Math.abs(slot.chairLocalX) + 0.25).toBeLessThanOrEqual(room.width / 2);
    }
  });
});

const makeAgent = (overrides: Partial<AgentIdentity> & { id: string }): AgentIdentity => ({
  id: overrides.id,
  name: overrides.name ?? overrides.id,
  type: overrides.type ?? 'UNKNOWN',
  roleTitle: overrides.roleTitle ?? 'Principal observado en ejecución',
  unitId: overrides.unitId ?? 'unit-unassigned',
  unitName: overrides.unitName,
  capabilities: overrides.capabilities ?? [],
  heartbeatStatus: overrides.heartbeatStatus ?? 'UNKNOWN',
  lastHeartbeatAt: overrides.lastHeartbeatAt ?? null,
  status: overrides.status ?? 'UNKNOWN',
  operationalState: overrides.operationalState ?? 'DESCONOCIDO',
  credentialStatus: overrides.credentialStatus ?? 'DISABLED',
  currentAssignments: overrides.currentAssignments ?? [],
  authorityBoundary: overrides.authorityBoundary ?? 'Sin concesiones de proyecto persistidas.',
  evidenceDescription:
    overrides.evidenceDescription ??
    'Identidad derivada de ejecuciones persistidas; sin perfil organizativo declarativo.',
});

describe('Phase 1 & 2 (Iteración 2): resolveLiveOrganizationAttribution & buildCorporateCampusLayout', () => {
  it('uses the same adaptive planner for DEMO units instead of the fixed OFFICE_ROOMS catalog', () => {
    const units = [unit('sim-west', 'WEST'), unit('sim-north', 'NORTH')];
    const agents = [makeAgent({ id: 'sim-agent', unitId: 'sim-west', credentialStatus: 'ENABLED', isSyntheticDemo: true })];
    const layout = buildCorporateCampusLayout(units, agents, { isDemo: true });

    expect(layout.rooms.map(({ id }) => id)).toEqual(['sim-north', 'sim-west']);
    expect(layout.rooms.some(({ id }) => id.startsWith('unit-'))).toBe(false);
    expect(layout.rooms.find(({ id }) => id === 'sim-west')?.workstationCapacity).toBe(1);
    expect(layout.rooms.find(({ id }) => id === 'sim-north')?.workstationCapacity).toBe(0);
    expect(layout.normalizedAgents[0].unitId).toBe('sim-west');
    expect(layout.diagnostics.headline).toContain('DEMO');
  });

  it('diagnoses the 7 live PostgreSQL principals truthfully without inventing departments from names or LLM models', () => {
    const liveUnits = [unit('unit-unassigned', 'UNKNOWN', 'Adscripción desconocida')];
    const liveAgents: AgentIdentity[] = [
      makeAgent({ id: 'aao-selfdev-d60cd366b26d', name: 'aao-selfdev-d60cd366b26d' }),
      makeAgent({ id: 'aao-implementer-202610251730', name: 'aao-implementer-202610251730' }),
      makeAgent({ id: 'aao-implementer-202610251032', name: 'aao-implementer-202610251032' }),
      makeAgent({ id: 'codex-self-development', name: 'codex-self-development' }),
      makeAgent({ id: 'aao-selfdev-impl-c394ed6f08b241399e8aa79776f7b18b' }),
      makeAgent({
        id: 'aao-auditor-202610251032',
        roleTitle: 'Principal observado como revisor',
        evidenceDescription: 'Identidad derivada de una revisión persistida.',
      }),
      makeAgent({
        id: 'aao-auditor-202610251730',
        roleTitle: 'Principal observado como revisor',
        evidenceDescription: 'Identidad derivada de una revisión persistida.',
      }),
    ];

    const result = resolveLiveOrganizationAttribution(liveUnits, liveAgents);

    expect(result.canonicalUnits).toEqual([]);
    expect(result.diagnostics.canonicalUnitsCount).toBe(0);
    expect(result.diagnostics.hasOnlyUnassignedUnit).toBe(true);
    expect(result.diagnostics.unassignedAgentsCount).toBe(7);
    expect(result.diagnostics.disabledCredentialsCount).toBe(7);
    expect(result.diagnostics.breakdown.executionNoProfile).toBe(5);
    expect(result.diagnostics.breakdown.reviewNoProfile).toBe(2);
    // Must NEVER invent engineering or audit units from 'implementer' or 'auditor' in the agent ID
    for (const agent of result.normalizedAgents) {
      expect(agent.unitId).toBe('unit-unassigned');
    }
  });

  it('resolves canonical units by id, code, or unitName and flags orphan unit references accurately', () => {
    const units = [
      unit('unit-unassigned', 'UNKNOWN', 'Adscripción desconocida'),
      unit('unit-eng', 'ENG', 'Ingeniería de Software'),
      unit('unit-audit', 'AUDIT', 'Auditoría Independiente'),
    ];
    const agents: AgentIdentity[] = [
      makeAgent({ id: 'ag-by-id', unitId: 'unit-eng', credentialStatus: 'ENABLED' }),
      makeAgent({ id: 'ag-by-code', unitId: 'AUDIT', credentialStatus: 'ENABLED' }),
      makeAgent({
        id: 'ag-by-name',
        unitId: 'unit-unassigned',
        unitName: 'Ingeniería de Software',
        credentialStatus: 'ENABLED',
      }),
      makeAgent({ id: 'ag-orphan', unitId: 'unit-deleted-99', credentialStatus: 'ENABLED' }),
    ];

    const { normalizedAgents, diagnostics } = resolveLiveOrganizationAttribution(units, agents);
    const byId = new Map(normalizedAgents.map((a) => [a.id, a]));

    expect(byId.get('ag-by-id')?.unitId).toBe('unit-eng');
    expect(byId.get('ag-by-code')?.unitId).toBe('unit-audit');
    expect(byId.get('ag-by-name')?.unitId).toBe('unit-eng');
    expect(byId.get('ag-orphan')?.unitId).toBe('unit-unassigned');
    expect(diagnostics.resolvedAgentsCount).toBe(3);
    expect(diagnostics.unassignedAgentsCount).toBe(1);
    expect(diagnostics.breakdown.orphanUnitRef).toBe(1);
    expect(diagnostics.byAgentId.get('ag-orphan')?.reason).toBe('ORPHAN_UNIT_REFERENCE');
  });

  it('produces arrival-order-invariant compact neighborhoods, keeps exact counts, and routes to the entry', () => {
    const unitsOrderA = [
      unit('unit-unassigned', 'UNKNOWN', 'Adscripción desconocida'),
      unit('unit-ops', 'OPS', 'Operaciones'),
      unit('unit-eng', 'ENG', 'Ingeniería'),
      unit('unit-audit', 'AUDIT', 'Auditoría'),
    ];
    const unitsOrderB = [...unitsOrderA].reverse();

    const agentsOrderA = Array.from({ length: 7 }, (_, i) =>
      makeAgent({ id: `unassigned-worker-${i}`, unitId: 'unit-unassigned' })
    ).concat([
      makeAgent({ id: 'eng-worker-1', unitId: 'unit-eng', credentialStatus: 'ENABLED' }),
    ]);
    const agentsOrderB = [...agentsOrderA].reverse();

    const layoutA = buildCorporateCampusLayout(unitsOrderA, agentsOrderA, { isDemo: false });
    const layoutB = buildCorporateCampusLayout(unitsOrderB, agentsOrderB, { isDemo: false });

    expect(layoutA.rooms).toEqual(layoutB.rooms);
    expect(layoutA.normalizedAgents).toEqual(layoutB.normalizedAgents);

    // There is no reserved central plaza: the occupied work neighborhood may
    // use the origin, and circulation is anchored to the actual main entry.
    expect(layoutA.rooms.some((room) => room.x === 0 && room.z === 0)).toBe(true);

    // Neutral/unassigned identities are not assigned fake department desks.
    const holdingRoom = layoutA.rooms.find((r) => r.id === 'unit-unassigned');
    expect(holdingRoom).toBeDefined();
    expect(holdingRoom?.kind).toBe('unassigned-holding');
    expect(holdingRoom?.workstationCapacity).toBe(0);

    // Verify navigable graph connects the building entry to every doorway and aisle.
    const navGraph = buildCampusNavGraph(layoutA.rooms);
    expect(navGraph.nodes.has('main-entry')).toBe(true);
    expect([...navGraph.nodes.keys()].some((id) => id.startsWith('atrium-ring-'))).toBe(false);
    const reachable = new Set(['main-entry']);
    const pending = ['main-entry'];
    while (pending.length > 0) {
      const current = pending.shift()!;
      for (const neighbor of navGraph.adjacency.get(current) ?? []) {
        if (reachable.has(neighbor)) continue;
        reachable.add(neighbor);
        pending.push(neighbor);
      }
    }
    for (const room of layoutA.rooms) {
      expect(navGraph.nodes.has(`doorway-${room.id}`)).toBe(true);
      expect(navGraph.nodes.has(`aisle-${room.id}`)).toBe(true);
      expect(navGraph.corridors.some((c) => c.fromRoomId === room.id)).toBe(true);
      expect(reachable.has(`aisle-${room.id}`)).toBe(true);
    }
  });

  it('uses deterministic free-form neighborhood candidates rather than a fixed world grid', () => {
    const requests = Array.from({ length: 7 }, (_, index) => ({
      id: `zone-${index}`,
      parentId: null,
      width: 4.8,
      depth: 4.2,
    }));
    const first = planOfficeZones(requests);
    expect(planOfficeZones(requests)).toEqual(first);
    expect(first[0]).toMatchObject({ x: 0, z: 0 });
    expect(first.some((zone) => Math.abs(zone.x / 8 - Math.round(zone.x / 8)) > 0.02 ||
      Math.abs(zone.z / 6.5 - Math.round(zone.z / 6.5)) > 0.02)).toBe(true);
    for (let left = 0; left < first.length; left += 1) {
      for (let right = left + 1; right < first.length; right += 1) {
        const a = first[left];
        const b = first[right];
        expect(Math.abs(a.x - b.x) < (a.width + b.width) / 2 + WORK_NEIGHBORHOOD_CLEARANCE_METERS &&
          Math.abs(a.z - b.z) < (a.depth + b.depth) / 2 + WORK_NEIGHBORHOOD_CLEARANCE_METERS).toBe(false);
      }
    }
  });

  it('routes campus walkways without cutting through another department interior', () => {
    const units = Array.from({ length: 16 }, (_, index) =>
      unit(`unit-route-${String(index).padStart(2, '0')}`, `R${index}`, `Routing ${index}`),
    );
    const { rooms } = buildCorporateCampusLayout(units, [], { isDemo: false });
    const corridors = buildCampusNavGraph(rooms).corridors;

    for (const corridor of corridors) {
      for (const room of rooms) {
        for (let index = 1; index < corridor.points.length; index += 1) {
          const start = corridor.points[index - 1];
          const end = corridor.points[index];
          for (let step = 1; step < 100; step += 1) {
            const t = step / 100;
            const x = start.x + (end.x - start.x) * t;
            const z = start.z + (end.z - start.z) * t;
            const insideX = Math.abs(x - room.x) < room.width / 2 - 0.1;
            const insideZ = Math.abs(z - room.z) < room.depth / 2 - 0.1;
            expect(insideX && insideZ, `${corridor.id} crosses ${room.id}`).toBe(false);
          }
        }
      }
    }
  });

  it('keeps circulation routable for growing LIVE neighborhoods with mixed desk counts', () => {
    for (const departmentCount of [1, 2, 4, 8, 16, 32]) {
      const units = Array.from({ length: departmentCount }, (_, index) =>
        unit(`unit-growth-${String(index).padStart(2, '0')}`, `G${index}`, `Growth ${index}`),
      );
      const agents = units.flatMap((department, index) =>
        Array.from({ length: index % 9 }, (_, agentIndex) =>
          makeAgent({ id: `${department.id}-agent-${agentIndex}`, unitId: department.id, credentialStatus: 'ENABLED' }),
        ),
      );

      expect(() => buildCorporateCampusLayout(units, agents, { isDemo: false })).not.toThrow();
    }
  });

  it('keeps the executive neighborhood connected across large LIVE organizations', () => {
    for (const departmentCount of [2, 16, 32]) {
      for (const executiveAgentCount of [0, 1, 3, 8]) {
        const units = [unit('unit-exec', 'EXEC', 'Dirección Ejecutiva'), ...Array.from(
          { length: departmentCount - 1 },
          (_, index) => unit(`unit-route-${String(index).padStart(2, '0')}`, `R${index}`, `Routing ${index}`),
        )];
        const agents = units.flatMap((department, index) =>
          Array.from({ length: index === 0 ? executiveAgentCount : index % 9 }, (_, agentIndex) => makeAgent({
            id: `${department.id}-agent-${agentIndex}`,
            unitId: department.id,
            credentialStatus: 'ENABLED',
          })),
        );

        expect(() => buildCorporateCampusLayout(units, agents, { isDemo: false })).not.toThrow();
      }
    }
  });

  it('keeps routes available across deterministic irregular executive organizations', () => {
    // Exercise layouts with unbalanced trees and varied executive occupancy,
    // rather than only uniformly numbered, flat department lists.
    let state = 0x5173;
    const next = (max: number) => {
      state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
      return state % max;
    };
    for (let sample = 0; sample < 30; sample += 1) {
      const count = 1 + next(40);
      const units = Array.from({ length: count }, (_, index) => {
        const id = index === 0 ? 'unit-exec' : `irregular-${sample}-${index}`;
        const parentIndex = index > 1 && next(3) === 0 ? next(index) : -1;
        return unit(
          id,
          `U${index}`,
          index === 0 ? 'Dirección Ejecutiva' : `Área ${sample}-${index}`,
          parentIndex >= 0 ? (parentIndex === 0 ? 'unit-exec' : `irregular-${sample}-${parentIndex}`) : null,
        );
      });
      const agents = units.flatMap((department, index) => Array.from(
        { length: index === 0 ? next(10) : next(9) },
        (_, agentIndex) => makeAgent({
          id: `${department.id}-agent-${agentIndex}`,
          unitId: department.id,
          credentialStatus: 'ENABLED',
        }),
      ));

      expect(() => buildCorporateCampusLayout(units, agents, { isDemo: false })).not.toThrow();
    }
  }, 20_000);

  it('preserves positions and routes after existing departments gain or lose agents', () => {
    const units = [
      unit('unit-exec', 'EXEC', 'Dirección Ejecutiva'),
      unit('unit-audit', 'AUDIT', 'Auditoría Independiente'),
      unit('unit-eng', 'ENG', 'Ingeniería'),
      unit('unit-ops', 'OPS', 'Operaciones'),
    ];
    let previousRooms: ReturnType<typeof buildCorporateCampusLayout>['rooms'] = [];

    for (const counts of [[0, 0, 0, 0], [1, 3, 8, 1], [8, 1, 3, 0], [0, 0, 0, 0], [1, 3, 8, 1]] as const) {
      const agents = units.flatMap((department, unitIndex) =>
        Array.from({ length: counts[unitIndex] }, (_, agentIndex) =>
          makeAgent({
            id: `${department.id}-agent-${agentIndex}`,
            unitId: department.id,
            credentialStatus: 'ENABLED',
          }),
        ),
      );
      const layout = buildCorporateCampusLayout(units, agents, { isDemo: false, previousRooms });
      expect(() => buildCampusNavGraph(layout.rooms)).not.toThrow();
      expect(layout.rooms).toHaveLength(units.length);

      const byId = new Map(layout.rooms.map((room) => [room.id, room]));
      for (const room of previousRooms) {
        const next = byId.get(room.id);
        if (next && next.width === room.width && next.depth === room.depth) {
          expect(next).toMatchObject({ x: room.x, z: room.z });
        }
      }
      previousRooms = layout.rooms;
    }
  });

  it('keeps an empty LIVE organization free of synthetic rooms', () => {
    const layout = buildCorporateCampusLayout([], [], { isDemo: false });
    expect(layout.rooms).toEqual([]);
    expect(layout.effectiveUnits).toEqual([]);
    expect(layout.normalizedAgents).toEqual([]);
  });

  it('keeps LIVE organizational zones stable when additional units are added', () => {
    const initialUnits = Array.from({ length: 12 }, (_, index) =>
      unit(`unit-${String(index).padStart(2, '0')}`, `D${index}`, `Departamento ${index}`)
    );
    const initial = buildCorporateCampusLayout(initialUnits, [], { isDemo: false });
    const expanded = buildCorporateCampusLayout(
      [...initialUnits, unit('unit-12', 'D12', 'Departamento 12')],
      [],
      { isDemo: false, previousRooms: initial.rooms },
    );

    const expandedById = new Map(expanded.rooms.map((room) => [room.id, room]));
    for (const room of initial.rooms) {
      expect(expandedById.get(room.id)).toMatchObject({ x: room.x, z: room.z });
    }
  });

  it('does not infer temporary squad status from organizational parentage', () => {
    const parent = unit('unit-eng', 'ENG', 'Ingeniería');
    const child = unit('unit-eng-child', 'ENG-PLATFORM', 'Plataforma', parent.id);
    const layout = buildCorporateCampusLayout([parent, child], [], { isDemo: false });
    const childRoom = layout.rooms.find((room) => room.id === child.id);
    expect(childRoom?.kind).toBe('canonical-department');
  });

  it('does not infer architectural roles from department IDs and keeps doorway compatibility geometry', () => {
    const units = [
      unit('unit-exec', 'EXEC', 'Dirección Ejecutiva'),
      unit('unit-audit', 'AUDIT', 'Auditoría Independiente'),
      unit('unit-subdivision-01', 'SUB-01', 'Subunidad de Modernización Frontend', 'unit-eng'),
      unit('unit-eng', 'ENG', 'Ingeniería de Software'),
    ];
    const agents = [
      makeAgent({ id: 'ag-exec', unitId: 'unit-exec' }),
      makeAgent({ id: 'ag-audit', unitId: 'unit-audit' }),
      makeAgent({ id: 'ag-squad', unitId: 'unit-squad-01' }),
      makeAgent({ id: 'ag-eng', unitId: 'unit-eng' }),
    ];

    const layout = buildCorporateCampusLayout(units, agents, { isDemo: false });

    const execRoom = layout.rooms.find((r) => r.id === 'unit-exec')!;
    expect(execRoom).toBeDefined();
    expect(execRoom.kind).toBe('executive-suite');
    expect(execRoom.floorFinish).toBe('hardwood-walnut');
    expect(execRoom.doorway).toBeDefined();
    expect(execRoom.doorway?.width).toBe(1.4);
    expect(execRoom.glassWalls).toBeDefined();
    expect(execRoom.glassWalls?.length).toBe(5);

    const auditRoom = layout.rooms.find((r) => r.id === 'unit-audit')!;
    expect(auditRoom).toBeDefined();
    expect(auditRoom.kind).toBe('audit-enclave');
    expect(auditRoom.floorFinish).toBe('high-security-frosted');
    expect(auditRoom.glassWalls?.some((w) => w.hasManifestationBand)).toBe(true);

    const subdivisionRoom = layout.rooms.find((r) => r.id === 'unit-subdivision-01')!;
    expect(subdivisionRoom).toBeDefined();
    expect(subdivisionRoom.kind).toBe('canonical-department');
    expect(subdivisionRoom.floorFinish).toBe('acoustic-carpet');

    const engRoom = layout.rooms.find((r) => r.id === 'unit-eng')!;
    expect(engRoom).toBeDefined();
    expect(engRoom.kind).toBe('canonical-department');
    expect(engRoom.floorFinish).toBe('acoustic-carpet');

    // Every doorway must match the navigation graph doorway node position exactly
    const navGraph = buildCampusNavGraph(layout.rooms);
    for (const room of layout.rooms) {
      const node = navGraph.nodes.get(`doorway-${room.id}`);
      expect(node).toBeDefined();
      expect(node?.x).toBeCloseTo(room.doorway!.x);
      expect(node?.z).toBeCloseTo(room.doorway!.z);
    }
  });
});
