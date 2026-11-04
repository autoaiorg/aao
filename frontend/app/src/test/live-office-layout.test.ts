import { describe, expect, it } from 'vitest';
import type { AgentIdentity, OrgUnit } from '../domain/models';
import {
  buildCampusNavGraph,
  buildCorporateCampusLayout,
  buildLiveOfficeRooms,
  resolveLiveOrganizationAttribution,
} from '../features/office/liveOfficeLayout';
import { buildDepartmentInteriorLayout } from '../features/office/engine/officeLifeEngine';

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
  it('reserves declared staffing capacity without materializing unobserved agents', () => {
    const planned = { ...unit('unit-planned', 'PLAN'), standingCount: 12, ephemeralCount: 3 };
    const { rooms, normalizedAgents } = buildCorporateCampusLayout([planned], [], { isDemo: false });
    const room = rooms.find(({ id }) => id === planned.id)!;

    expect(room.workstationCapacity).toBeGreaterThanOrEqual(15);
    expect(normalizedAgents).toEqual([]);
    expect(room.width).toBeGreaterThan(4.8);
  });

  it('fits workstation geometry inside expanded departments for teams over ten', () => {
    const team = unit('unit-large-team', 'LARGE', 'Large team');
    const agents = Array.from({ length: 25 }, (_, index) =>
      makeAgent({ id: `large-agent-${index}`, unitId: team.id })
    );
    const room = buildCorporateCampusLayout([team], agents).rooms.find(({ id }) => id === team.id)!;
    const interior = buildDepartmentInteriorLayout(room);

    expect(room.workstationCapacity).toBeGreaterThanOrEqual(agents.length);
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

  it('produces arrival-order-invariant corporate campus layouts, avoids Central Atrium (0,0) collisions, and scales capacity for 7+ agents', () => {
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

    // Verify no room overlaps the Central Coordination Atrium at (0, 0)
    for (const room of layoutA.rooms) {
      const distFromAtrium = Math.hypot(room.x, room.z);
      expect(distFromAtrium).toBeGreaterThanOrEqual(4.5);
    }

    // Verify the unassigned holding wing has distinct kind and capacity >= 8 for 7 agents
    const holdingRoom = layoutA.rooms.find((r) => r.id === 'unit-unassigned');
    expect(holdingRoom).toBeDefined();
    expect(holdingRoom?.kind).toBe('unassigned-holding');
    expect(holdingRoom?.workstationCapacity).toBeGreaterThanOrEqual(8);

    // Verify navigable graph connects Atrium to every room doorway and aisle
    const navGraph = buildCampusNavGraph(layoutA.rooms);
    expect(navGraph.nodes.has('atrium-center')).toBe(true);
    const reachable = new Set(['atrium-center']);
    const pending = ['atrium-center'];
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

  it('assigns adaptive zone types, realistic floor finishes, and computes architectural glass walls with doorway portals', () => {
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
    // Audit enclave must have acoustic manifestation bands on its glass walls
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
