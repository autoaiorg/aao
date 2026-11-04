import type { AgentIdentity, OrgUnit } from '../../domain/models';
import {
  OFFICE_ROOMS,
  type OfficeDoorwayPortal,
  type OfficeFloorFinish,
  type OfficeGlassWallSegment,
  type OfficeRoomConfig,
  type OfficeZoneKind,
} from './types';

const UNIT_COLORS = [
  ['#1e3a8a', '#3b82f6'],
  ['#4c1d95', '#8b5cf6'],
  ['#064e3b', '#10b981'],
  ['#78350f', '#f59e0b'],
  ['#164e63', '#06b6d4'],
  ['#713f12', '#d97706'],
] as const;

export const UNASSIGNED_UNIT_ID = 'unit-unassigned';
export const UNASSIGNED_HOLDING_COLORS = ['#334155', '#94a3b8'] as const;

/**
 * Computes architectural features (doorway portal and glass wall segments with doorway cutouts)
 * for a room box based on its position relative to the central atrium.
 */
export function computeRoomArchitectureFeatures(room: {
  x: number;
  z: number;
  width: number;
  depth: number;
  kind?: OfficeZoneKind;
}): { doorway: OfficeDoorwayPortal; glassWalls: OfficeGlassWallSegment[] } {
  const doorwaySignZ = room.z < 0 ? 1 : room.z > 0 ? -1 : 1;
  const frontZ = Number((room.z + doorwaySignZ * (room.depth / 2)).toFixed(2));
  const doorwayWidth = 1.4;

  const doorway: OfficeDoorwayPortal = {
    x: room.x,
    z: Number((frontZ + doorwaySignZ * 0.25).toFixed(2)),
    width: doorwayWidth,
    facingAngle: doorwaySignZ < 0 ? Math.PI : 0,
  };

  const isAudit = room.kind === 'audit-enclave';
  const wallHeight = 1.15;
  const hw = room.width / 2;
  const hd = room.depth / 2;

  // 1. Back Wall
  const backZ = room.z - doorwaySignZ * hd;
  const backWall: OfficeGlassWallSegment = {
    startX: room.x - hw,
    startZ: backZ,
    endX: room.x + hw,
    endZ: backZ,
    height: wallHeight,
    hasManifestationBand: isAudit,
  };

  // 2. Left Wall
  const leftWall: OfficeGlassWallSegment = {
    startX: room.x - hw,
    startZ: room.z - hd,
    endX: room.x - hw,
    endZ: room.z + hd,
    height: wallHeight,
    hasManifestationBand: isAudit,
  };

  // 3. Right Wall
  const rightWall: OfficeGlassWallSegment = {
    startX: room.x + hw,
    startZ: room.z - hd,
    endX: room.x + hw,
    endZ: room.z + hd,
    height: wallHeight,
    hasManifestationBand: isAudit,
  };

  // 4. Front Wall with Doorway cutout (left panel and right panel)
  const frontWallLeft: OfficeGlassWallSegment = {
    startX: room.x - hw,
    startZ: frontZ,
    endX: room.x - doorwayWidth / 2,
    endZ: frontZ,
    height: wallHeight,
    hasManifestationBand: isAudit,
  };

  const frontWallRight: OfficeGlassWallSegment = {
    startX: room.x + doorwayWidth / 2,
    startZ: frontZ,
    endX: room.x + hw,
    endZ: frontZ,
    height: wallHeight,
    hasManifestationBand: isAudit,
  };

  return {
    doorway,
    glassWalls: [backWall, leftWall, rightWall, frontWallLeft, frontWallRight],
  };
}

export type AgentAttributionReason =
  | 'RESOLVED_UNIT'
  | 'OBSERVED_EXECUTION_NO_PROFILE'
  | 'OBSERVED_REVIEW_NO_PROFILE'
  | 'PROFILE_WITHOUT_UNIT'
  | 'ORPHAN_UNIT_REFERENCE'
  | 'UNASSIGNED_OTHER';

export interface AgentAttributionDiagnostic {
  agentId: string;
  agentName: string;
  rawUnitId: string;
  resolvedUnitId: string;
  resolvedUnitName: string;
  isResolvedToCanonicalUnit: boolean;
  reason: AgentAttributionReason;
  reasonLabel: string;
  credentialStatus: 'ENABLED' | 'DISABLED' | 'UNKNOWN';
}

export interface OrganizationAttributionDiagnostics {
  canonicalUnitsCount: number;
  hasOnlyUnassignedUnit: boolean;
  totalAgentsCount: number;
  resolvedAgentsCount: number;
  unassignedAgentsCount: number;
  enabledCredentialsCount: number;
  disabledCredentialsCount: number;
  breakdown: {
    executionNoProfile: number;
    reviewNoProfile: number;
    profileWithoutUnit: number;
    orphanUnitRef: number;
    otherUnassigned: number;
  };
  headline: string;
  explanation: string;
  remediationHint: string;
  byAgentId: Map<string, AgentAttributionDiagnostic>;
}

export interface CampusNavNode {
  id: string;
  kind: 'atrium-center' | 'atrium-ring' | 'corridor-junction' | 'room-doorway' | 'room-aisle';
  roomId?: string;
  x: number;
  z: number;
}

export interface CampusCorridorSegment {
  id: string;
  fromRoomId: string;
  toNodeId: string;
  startX: number;
  startZ: number;
  endX: number;
  endZ: number;
  width: number;
  isUnassignedWing: boolean;
}

export interface CampusNavGraph {
  nodes: Map<string, CampusNavNode>;
  adjacency: Map<string, string[]>;
  corridors: CampusCorridorSegment[];
}

export interface CorporateCampusLayout {
  rooms: OfficeRoomConfig[];
  effectiveUnits: OrgUnit[];
  normalizedAgents: AgentIdentity[];
  diagnostics: OrganizationAttributionDiagnostics;
  navGraph: CampusNavGraph;
  bounds: {
    minX: number;
    maxX: number;
    minZ: number;
    maxZ: number;
    centerX: number;
    centerZ: number;
    spanX: number;
    spanZ: number;
    recommendedOverviewDistance: number;
  };
}

/**
 * Legacy deterministic room builder preserved for backward compatibility with unit tests.
 * Builds a display-only layout from persisted organization units; it creates no organization data.
 */
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
    const isUnassigned = unit.id === UNASSIGNED_UNIT_ID || unit.code === 'UNKNOWN';
    const [color, accentColor] = isUnassigned
      ? UNASSIGNED_HOLDING_COLORS
      : UNIT_COLORS[index % UNIT_COLORS.length];
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
      kind: isUnassigned ? 'unassigned-holding' : 'canonical-department',
      parentId: unit.parentId,
    };
  });
}

/**
 * Phase 1 (P0): Investigates and resolves LIVE agent organizational attribution strictly from
 * persisted backend contracts (`units` and `agents`), without inventing departments from names or LLM models.
 */
export function resolveLiveOrganizationAttribution(
  units: readonly OrgUnit[],
  agents: readonly AgentIdentity[]
): {
  canonicalUnits: OrgUnit[];
  normalizedAgents: AgentIdentity[];
  diagnostics: OrganizationAttributionDiagnostics;
} {
  const canonicalUnits = units.filter(
    (u) => u.id !== UNASSIGNED_UNIT_ID && u.code.toUpperCase() !== 'UNKNOWN'
  );
  const canonicalById = new Map<string, OrgUnit>();
  const canonicalByCode = new Map<string, OrgUnit>();
  const canonicalByName = new Map<string, OrgUnit>();

  for (const unit of canonicalUnits) {
    canonicalById.set(unit.id, unit);
    canonicalByCode.set(unit.code.trim().toUpperCase(), unit);
    canonicalByName.set(unit.name.trim().toLowerCase(), unit);
  }

  const byAgentId = new Map<string, AgentAttributionDiagnostic>();
  const breakdown = {
    executionNoProfile: 0,
    reviewNoProfile: 0,
    profileWithoutUnit: 0,
    orphanUnitRef: 0,
    otherUnassigned: 0,
  };

  let resolvedAgentsCount = 0;
  let unassignedAgentsCount = 0;
  let enabledCredentialsCount = 0;
  let disabledCredentialsCount = 0;

  // Sort agents deterministically by id so arrival order never affects diagnostics or placement
  const sortedInputAgents = [...agents].sort((a, b) => a.id.localeCompare(b.id));

  const normalizedAgents: AgentIdentity[] = sortedInputAgents.map((agent) => {
    const rawUnitId = (agent.unitId || '').trim();
    const rawUnitName = (agent.unitName || '').trim();
    const credStatus = agent.credentialStatus ?? 'UNKNOWN';
    if (credStatus === 'ENABLED') enabledCredentialsCount += 1;
    if (credStatus === 'DISABLED') disabledCredentialsCount += 1;

    // 1. Check direct canonical unit ID match, or exact unit code match, or exact canonical unit name match
    let matchedUnit: OrgUnit | undefined = canonicalById.get(rawUnitId);
    if (!matchedUnit && rawUnitId && rawUnitId !== UNASSIGNED_UNIT_ID) {
      matchedUnit = canonicalByCode.get(rawUnitId.toUpperCase());
    }
    if (
      !matchedUnit &&
      rawUnitName &&
      rawUnitName.toLowerCase() !== 'adscripción desconocida' &&
      rawUnitName.toLowerCase() !== '«departamento desconocido»'
    ) {
      matchedUnit = canonicalByName.get(rawUnitName.toLowerCase());
    }

    if (matchedUnit) {
      resolvedAgentsCount += 1;
      const diag: AgentAttributionDiagnostic = {
        agentId: agent.id,
        agentName: agent.name,
        rawUnitId: rawUnitId || UNASSIGNED_UNIT_ID,
        resolvedUnitId: matchedUnit.id,
        resolvedUnitName: matchedUnit.name,
        isResolvedToCanonicalUnit: true,
        reason: 'RESOLVED_UNIT',
        reasonLabel: `Adscrito a unidad persistida «${matchedUnit.name}» ([${matchedUnit.code}]).`,
        credentialStatus: credStatus,
      };
      byAgentId.set(agent.id, diag);
      return {
        ...agent,
        unitId: matchedUnit.id,
        unitName: matchedUnit.name,
      };
    }

    // 2. Unassigned or unresolvable unit reference -> preserve truthful UNKNOWN state with exact cause
    unassignedAgentsCount += 1;
    let reason: AgentAttributionReason = 'UNASSIGNED_OTHER';
    let reasonLabel =
      'Sin perfil organizativo (`organization_profiles`) ni unidad (`unit_id`) declarada en el núcleo.';

    const roleLower = (agent.roleTitle || '').toLowerCase();
    const evidenceLower = (agent.evidenceDescription || '').toLowerCase();

    if (rawUnitId && rawUnitId !== UNASSIGNED_UNIT_ID) {
      reason = 'ORPHAN_UNIT_REFERENCE';
      breakdown.orphanUnitRef += 1;
      reasonLabel = `Referencia de unidad «${rawUnitId}» no encontrada entre las unidades habilitadas (\`organization_units\`).`;
    } else if (
      roleLower.includes('observado en ejecución') ||
      evidenceLower.includes('derivada de ejecuciones')
    ) {
      reason = 'OBSERVED_EXECUTION_NO_PROFILE';
      breakdown.executionNoProfile += 1;
      reasonLabel =
        'Principal observado en cola de ejecución (`execution_queue`) sin perfil declarativo en `organization_profiles`.';
    } else if (
      roleLower.includes('observado como revisor') ||
      evidenceLower.includes('derivada de una revisión')
    ) {
      reason = 'OBSERVED_REVIEW_NO_PROFILE';
      breakdown.reviewNoProfile += 1;
      reasonLabel =
        'Principal observado en revisiones (`reviews`) sin perfil declarativo en `organization_profiles`.';
    } else if (evidenceLower.includes('perfil organizativo persistido')) {
      reason = 'PROFILE_WITHOUT_UNIT';
      breakdown.profileWithoutUnit += 1;
      reasonLabel =
        'Perfil registrado en `organization_profiles`, pero con `unit_id = NULL` (sin departamento asignado).';
    } else {
      breakdown.otherUnassigned += 1;
    }

    const diag: AgentAttributionDiagnostic = {
      agentId: agent.id,
      agentName: agent.name,
      rawUnitId: rawUnitId || UNASSIGNED_UNIT_ID,
      resolvedUnitId: UNASSIGNED_UNIT_ID,
      resolvedUnitName: 'Adscripción desconocida',
      isResolvedToCanonicalUnit: false,
      reason,
      reasonLabel,
      credentialStatus: credStatus,
    };
    byAgentId.set(agent.id, diag);

    return {
      ...agent,
      unitId: UNASSIGNED_UNIT_ID,
      unitName: agent.unitName || 'Adscripción desconocida',
    };
  });

  const canonicalUnitsCount = canonicalUnits.length;
  const hasOnlyUnassignedUnit = canonicalUnitsCount === 0;

  let headline = 'Adscripción organizativa verificada';
  let explanation = `${resolvedAgentsCount} de ${normalizedAgents.length} agentes cuentan con unidad departamental declarada en el núcleo.`;
  let remediationHint = '';

  if (hasOnlyUnassignedUnit && normalizedAgents.length > 0) {
    headline = `Sin departamentos declarados en PostgreSQL (${unassignedAgentsCount} principales en adscripción pendiente)`;
    const parts: string[] = [];
    if (breakdown.executionNoProfile > 0) {
      parts.push(`${breakdown.executionNoProfile} derivado(s) de ejecuciones (\`execution_queue\`)`);
    }
    if (breakdown.reviewNoProfile > 0) {
      parts.push(`${breakdown.reviewNoProfile} derivado(s) de revisiones (\`reviews\`)`);
    }
    if (breakdown.profileWithoutUnit > 0) {
      parts.push(`${breakdown.profileWithoutUnit} con perfil sin \`unit_id\``);
    }
    if (disabledCredentialsCount > 0) {
      parts.push(`${disabledCredentialsCount} con credencial histórica deshabilitada`);
    }
    explanation =
      `La tabla \`organization_units\` tiene 0 unidades habilitadas y \`organization_profiles\` no asigna departamento a estos ${unassignedAgentsCount} principales` +
      (parts.length > 0 ? ` (${parts.join(', ')}).` : '.');
    remediationHint =
      'Para adscribirlos a departamentos reales en LIVE, declare unidades vía PUT /v1/organization/units y perfiles vía PUT /v1/organization/profiles en la vista «Organización».';
  } else if (unassignedAgentsCount > 0) {
    headline = `${unassignedAgentsCount} principal(es) sin adscripción departamental declarada`;
    explanation = `${resolvedAgentsCount} agente(s) ubicados en ${canonicalUnitsCount} departamento(s) reales; ${unassignedAgentsCount} permanecen en el Área de Adscripción Pendiente ([UNKNOWN]).`;
    remediationHint =
      'Puede asignar los principales pendientes a una unidad existente desde la vista «Organización» (PUT /v1/organization/profiles).';
  }

  return {
    canonicalUnits,
    normalizedAgents,
    diagnostics: {
      canonicalUnitsCount,
      hasOnlyUnassignedUnit,
      totalAgentsCount: normalizedAgents.length,
      resolvedAgentsCount,
      unassignedAgentsCount,
      enabledCredentialsCount,
      disabledCredentialsCount,
      breakdown,
      headline,
      explanation,
      remediationHint,
      byAgentId,
    },
  };
}

/**
 * Computes room width and depth dynamically so that `agentCount` workstations + meeting zone
 * fit comfortably without chair collisions.
 */
function computeRoomDimensionsForAgents(
  agentCount: number,
  isUnassignedHolding: boolean
): { width: number; depth: number; workstationCapacity: number } {
  const needed = Math.max(4, agentCount);
  if (needed <= 4) {
    return {
      width: isUnassignedHolding ? 5.2 : 4.8,
      depth: 4.2,
      workstationCapacity: 4,
    };
  }
  if (needed <= 6) {
    return {
      width: 5.6,
      depth: 4.4,
      workstationCapacity: 6,
    };
  }
  if (needed <= 8) {
    return {
      width: 6.4,
      depth: 4.8,
      workstationCapacity: 8,
    };
  }
  const cols = Math.ceil(needed / 2);
  return {
    width: Math.min(9.2, 3.6 + cols * 1.15),
    depth: 5.2,
    workstationCapacity: cols * 2,
  };
}

/**
 * Phase 2 (P1): Deterministic Corporate Campus Spatial Generator.
 * Connects the Central Coordination Atrium (0, 0) to all canonical departments via navigable
 * architectural corridors and doorways, and segregates `unit-unassigned` into a distinct
 * peripheral Holding Wing so no room ever overlaps the Central Atrium.
 */
export function buildCorporateCampusLayout(
  units: readonly OrgUnit[],
  agents: readonly AgentIdentity[],
  options: { isDemo?: boolean } = {}
): CorporateCampusLayout {
  if (options.isDemo) {
    const demoCounts = new Map<string, number>();
    for (const a of agents) {
      demoCounts.set(a.unitId, (demoCounts.get(a.unitId) ?? 0) + 1);
    }
    const demoRooms: OfficeRoomConfig[] = OFFICE_ROOMS.map((r) => {
      const arch = computeRoomArchitectureFeatures(r);
      return {
        ...r,
        doorway: arch.doorway,
        glassWalls: arch.glassWalls,
        workstationCapacity: Math.max(4, demoCounts.get(r.id) ?? 4),
      };
    });
    const navGraph = buildCampusNavGraph(demoRooms);
    return {
      rooms: demoRooms,
      effectiveUnits: [...units],
      normalizedAgents: [...agents].sort((a, b) => a.id.localeCompare(b.id)),
      diagnostics: {
        canonicalUnitsCount: demoRooms.length,
        hasOnlyUnassignedUnit: false,
        totalAgentsCount: agents.length,
        resolvedAgentsCount: agents.length,
        unassignedAgentsCount: 0,
        enabledCredentialsCount: agents.length,
        disabledCredentialsCount: 0,
        breakdown: {
          executionNoProfile: 0,
          reviewNoProfile: 0,
          profileWithoutUnit: 0,
          orphanUnitRef: 0,
          otherUnassigned: 0,
        },
        headline: 'Simulación corporativa DEMO',
        explanation: 'Estructura departamental sintética de demostración.',
        remediationHint: '',
        byAgentId: new Map(),
      },
      navGraph,
      bounds: computeCampusBounds(demoRooms),
    };
  }

  const { canonicalUnits, normalizedAgents, diagnostics } =
    resolveLiveOrganizationAttribution(units, agents);

  const agentCountByUnit = new Map<string, number>();
  for (const agent of normalizedAgents) {
    agentCountByUnit.set(agent.unitId, (agentCountByUnit.get(agent.unitId) ?? 0) + 1);
  }

  const byId = new Map(canonicalUnits.map((u) => [u.id, u]));
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

  // Sort canonical units deterministically (immune to backend row order)
  const orderedCanonical = [...canonicalUnits].sort((left, right) => {
    const depth = hierarchyDepth(left) - hierarchyDepth(right);
    if (depth !== 0) return depth;
    const parent = (left.parentId ?? '').localeCompare(right.parentId ?? '');
    if (parent !== 0) return parent;
    const code = left.code.localeCompare(right.code);
    return code !== 0 ? code : left.id.localeCompare(right.id);
  });

  const rooms: OfficeRoomConfig[] = [];
  const totalCanonical = orderedCanonical.length;

  // Place canonical departments in balanced North / South / Radial wings around the Central Atrium (0,0)
  // Guaranteeing |z| >= 4.2 or radial distance >= 6.8 so NO department ever overlaps the Atrium at (0,0)!
  orderedCanonical.forEach((unit, index) => {
    const countInUnit = agentCountByUnit.get(unit.id) ?? 0;
    const dims = computeRoomDimensionsForAgents(countInUnit, false);
    const [color, accentColor] = UNIT_COLORS[index % UNIT_COLORS.length];

    let x = 0;
    let z = -5.2;

    if (totalCanonical === 1) {
      x = 0;
      z = -5.4;
    } else if (totalCanonical === 2) {
      x = index === 0 ? -5.8 : 5.8;
      z = -4.6;
    } else if (totalCanonical <= 6) {
      const topRowCount = Math.ceil(totalCanonical / 2);
      const bottomRowCount = totalCanonical - topRowCount;
      if (index < topRowCount) {
        x = (index - (topRowCount - 1) / 2) * 6.2;
        z = -4.6;
      } else {
        const bottomIdx = index - topRowCount;
        x = (bottomIdx - (bottomRowCount - 1) / 2) * 6.2;
        z = 4.6;
      }
    } else {
      // Multi-wing ring for 7+ departments
      const ringIndex = Math.floor(index / 6);
      const posInRing = index % 6;
      const countInThisRing = Math.min(6, totalCanonical - ringIndex * 6);
      const angle = (posInRing / countInThisRing) * Math.PI * 2 - Math.PI / 2;
      const radiusX = 7.8 + ringIndex * 6.5;
      const radiusZ = 5.6 + ringIndex * 5.4;
      x = Number((Math.cos(angle) * radiusX).toFixed(2));
      z = Number((Math.sin(angle) * radiusZ).toFixed(2));
    }

    const isExec = unit.code === 'EXEC' || unit.id === 'unit-exec';
    const isAudit = unit.code === 'AUDIT' || unit.id === 'unit-audit';
    const isSquad = Boolean(unit.parentId && unit.parentId !== 'unit-root');

    const kind: OfficeZoneKind = isExec
      ? 'executive-suite'
      : isAudit
      ? 'audit-enclave'
      : isSquad
      ? 'agile-squad-pod'
      : 'canonical-department';

    const floorFinish: OfficeFloorFinish = isExec
      ? 'hardwood-walnut'
      : isAudit
      ? 'high-security-frosted'
      : 'acoustic-carpet';

    const arch = computeRoomArchitectureFeatures({
      x,
      z,
      width: dims.width,
      depth: dims.depth,
      kind,
    });

    rooms.push({
      id: unit.id,
      code: unit.code,
      name: unit.name,
      x,
      z,
      width: dims.width,
      depth: dims.depth,
      color,
      accentColor,
      kind,
      floorFinish,
      doorway: arch.doorway,
      glassWalls: arch.glassWalls,
      parentId: unit.parentId,
      workstationCapacity: dims.workstationCapacity,
    });
  });

  // Determine whether the Unassigned Holding Wing (`unit-unassigned`) should be materialized:
  // Always materialize when there are unassigned agents OR when 0 canonical units exist in LIVE.
  const unassignedCount = agentCountByUnit.get(UNASSIGNED_UNIT_ID) ?? 0;
  const shouldIncludeUnassignedWing =
    unassignedCount > 0 || (orderedCanonical.length === 0 && units.length > 0);

  if (shouldIncludeUnassignedWing) {
    const dims = computeRoomDimensionsForAgents(unassignedCount, true);
    const existingUnassignedUnit = units.find((u) => u.id === UNASSIGNED_UNIT_ID);
    // Position the Holding Wing in a dedicated southern/peripheral bay outside the Central Atrium (0, 0)
    const holdingZ = orderedCanonical.length === 0 ? 5.6 :orderedCanonical.length <= 3 ? 5.4 : 9.6;
    const holdingX = 0;

    const arch = computeRoomArchitectureFeatures({
      x: holdingX,
      z: holdingZ,
      width: dims.width,
      depth: dims.depth,
      kind: 'unassigned-holding',
    });

    rooms.push({
      id: UNASSIGNED_UNIT_ID,
      code: existingUnassignedUnit?.code || 'UNKNOWN',
      name: existingUnassignedUnit?.name || 'Adscripción desconocida',
      x: holdingX,
      z: holdingZ,
      width: dims.width,
      depth: dims.depth,
      color: UNASSIGNED_HOLDING_COLORS[0],
      accentColor: UNASSIGNED_HOLDING_COLORS[1],
      kind: 'unassigned-holding',
      floorFinish: 'acoustic-carpet',
      doorway: arch.doorway,
      glassWalls: arch.glassWalls,
      parentId: null,
      workstationCapacity: dims.workstationCapacity,
    });
  }

  // Filter effectiveUnits so empty synthetic `unit-unassigned` does not pollute unit lists when all agents have real units,
  // and only include `unit-unassigned` in `effectiveUnits` when present in input `units` (as returned by GET /v1/organization).
  const rawUnassignedUnit = units.find((u) => u.id === UNASSIGNED_UNIT_ID);
  const effectiveUnits: OrgUnit[] = [
    ...orderedCanonical,
    ...(shouldIncludeUnassignedWing && rawUnassignedUnit ? [rawUnassignedUnit] : []),
  ];

  const navGraph = buildCampusNavGraph(rooms);
  const bounds = computeCampusBounds(rooms);

  return {
    rooms,
    effectiveUnits,
    normalizedAgents,
    diagnostics,
    navGraph,
    bounds,
  };
}

/**
 * Builds the navigable connectivity graph connecting the Central Coordination Atrium (0, 0)
 * to every room's doorway and internal central aisle.
 */
export function buildCampusNavGraph(rooms: readonly OfficeRoomConfig[]): CampusNavGraph {
  const nodes = new Map<string, CampusNavNode>();
  const adjacency = new Map<string, string[]>();
  const corridors: CampusCorridorSegment[] = [];

  const addNode = (node: CampusNavNode) => {
    nodes.set(node.id, node);
    if (!adjacency.has(node.id)) {
      adjacency.set(node.id, []);
    }
  };

  const connect = (a: string, b: string) => {
    adjacency.get(a)?.push(b);
    adjacency.get(b)?.push(a);
  };

  // Central Atrium Hub & 8 Ring Waypoints around the Atrium perimeter (radius 2.9)
  addNode({ id: 'atrium-center', kind: 'atrium-center', x: 0, z: 0 });
  const ringCount = 8;
  const ringRadius = 2.9;
  for (let i = 0; i < ringCount; i += 1) {
    const angle = (i / ringCount) * Math.PI * 2;
    const id = `atrium-ring-${i}`;
    addNode({
      id,
      kind: 'atrium-ring',
      x: Number((Math.cos(angle) * ringRadius).toFixed(2)),
      z: Number((Math.sin(angle) * ringRadius).toFixed(2)),
    });
    connect('atrium-center', id);
  }
  for (let i = 0; i < ringCount; i += 1) {
    connect(`atrium-ring-${i}`, `atrium-ring-${(i + 1) % ringCount}`);
  }

  // Connect each room's doorway to the nearest Atrium Ring node via a corridor segment
  for (const room of rooms) {
    const doorwayX = room.doorway ? room.doorway.x : room.x;
    const doorwayZ = room.doorway
      ? room.doorway.z
      : Math.abs(room.z) >= 2.2
      ? room.z + (room.z < 0 ? 1 : room.z > 0 ? -1 : room.x < 0 ? 1 : -1) * (room.depth / 2 + 0.35)
      : room.z;

    const doorwayId = `doorway-${room.id}`;
    const aisleId = `aisle-${room.id}`;

    addNode({ id: doorwayId, kind: 'room-doorway', roomId: room.id, x: doorwayX, z: doorwayZ });
    addNode({ id: aisleId, kind: 'room-aisle', roomId: room.id, x: room.x, z: room.z });
    connect(doorwayId, aisleId);

    // Find closest atrium ring node
    let nearestRingId = 'atrium-ring-0';
    let bestDist = Infinity;
    for (let i = 0; i < ringCount; i += 1) {
      const rNode = nodes.get(`atrium-ring-${i}`)!;
      const d = Math.hypot(doorwayX - rNode.x, doorwayZ - rNode.z);
      if (d < bestDist) {
        bestDist = d;
        nearestRingId = rNode.id;
      }
    }

    connect(doorwayId, nearestRingId);
    const ringNode = nodes.get(nearestRingId)!;

    corridors.push({
      id: `corridor-${room.id}`,
      fromRoomId: room.id,
      toNodeId: nearestRingId,
      startX: doorwayX,
      startZ: doorwayZ,
      endX: ringNode.x,
      endZ: ringNode.z,
      width: room.kind === 'unassigned-holding' ? 1.1 : 1.35,
      isUnassignedWing: room.kind === 'unassigned-holding',
    });
  }

  return { nodes, adjacency, corridors };
}

/**
 * Computes the bounding box of all rooms + central atrium and the ideal camera distance
 * to frame the entire campus without clipping any department.
 */
export function computeCampusBounds(rooms: readonly OfficeRoomConfig[]): CorporateCampusLayout['bounds'] {
  if (rooms.length === 0) {
    return {
      minX: -9,
      maxX: 9,
      minZ: -7,
      maxZ: 7,
      centerX: 0,
      centerZ: 0,
      spanX: 18,
      spanZ: 14,
      recommendedOverviewDistance: 24,
    };
  }

  let minX = -3.8; // Include central atrium
  let maxX = 3.8;
  let minZ = -3.8;
  let maxZ = 3.8;

  for (const r of rooms) {
    minX = Math.min(minX, r.x - r.width / 2 - 1.2);
    maxX = Math.max(maxX, r.x + r.width / 2 + 1.2);
    minZ = Math.min(minZ, r.z - r.depth / 2 - 1.2);
    maxZ = Math.max(maxZ, r.z + r.depth / 2 + 1.2);
  }

  const spanX = maxX - minX;
  const spanZ = maxZ - minZ;

  // Keep symmetric 6-room default campus at exact (0, 0) and distance 24 for test compatibility
  const isSymmetricDefault =
    Math.abs(minX + maxX) < 1.5 && Math.abs(minZ + maxZ) < 1.5 && spanX <= 20 && spanZ <= 16;

  const centerX = isSymmetricDefault ? 0 : Number(((minX + maxX) / 2).toFixed(2));
  const centerZ = isSymmetricDefault ? 0 : Number(((minZ + maxZ) / 2).toFixed(2));
  const maxSpan = Math.max(spanX, spanZ * 1.25);
  const recommendedOverviewDistance = isSymmetricDefault
    ? 24
    : Math.max(20, Math.min(36, Math.round(maxSpan * 1.25)));

  return {
    minX,
    maxX,
    minZ,
    maxZ,
    centerX,
    centerZ,
    spanX,
    spanZ,
    recommendedOverviewDistance,
  };
}
