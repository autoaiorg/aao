import type { AgentIdentity } from '../../../domain/models';
import type { OfficeRoomConfig } from '../types';

/**
 * High-level visual activity state for an agent in the 3D Office.
 * Strictly separated from business state through explicit provenance.
 */
export type AgentVisualActivityKind =
  | 'TYPING_DEV'
  | 'TYPING_AUDIT'
  | 'TYPING_DOCS'
  | 'CONVERSING'
  | 'WALKING'
  | 'IDLE_DESK'
  | 'DISCONNECTED'
  | 'UNKNOWN_NEUTRAL';

/**
 * Explicit provenance of the visual representation so UI and users
 * never confuse ambient animation or demo simulation with LIVE backend evidence.
 */
export type ActivityProvenance =
  | 'LIVE_VERIFIED_EVIDENCE'
  | 'AMBIENT_ANIMATION'
  | 'DEMO_SIMULATION'
  | 'NEUTRAL_NO_EVIDENCE';

export interface ProjectedAgentActivity {
  agentId: string;
  kind: AgentVisualActivityKind;
  provenance: ActivityProvenance;
  label: string;
  shortBadge: string;
  detail: string;
  isLeaseExpired: boolean;
  activeTaskId: string | null;
  activeProjectId: string | null;
  conversationPartnerId: string | null;
}

export interface WorkstationSlot {
  slotIndex: number;
  /** Local coordinates relative to room center */
  deskLocalX: number;
  deskLocalZ: number;
  /** Chair position where the agent sits */
  chairLocalX: number;
  chairLocalZ: number;
  /** World coordinates */
  deskWorldX: number;
  deskWorldZ: number;
  chairWorldX: number;
  chairWorldZ: number;
  /** Rotation in radians so the seated agent faces the monitor on the desk */
  facingAngle: number;
}

export interface MeetingSpot {
  spotIndex: number;
  localX: number;
  localZ: number;
  worldX: number;
  worldZ: number;
  facingAngle: number;
}

export interface DepartmentInteriorLayout {
  roomId: string;
  workstations: WorkstationSlot[];
  meetingTableLocal: { x: number; z: number };
  meetingSpots: MeetingSpot[];
  corridorEntryWorld: { x: number; z: number };
}

export interface PlannedAgentPlacement {
  agentId: string;
  unitId: string;
  activity: ProjectedAgentActivity;
  workstationSlot: WorkstationSlot;
  targetWorldX: number;
  targetWorldZ: number;
  targetFacingAngle: number;
  isSeated: boolean;
  /** Obstacle-free corridor waypoints when activity.kind === 'WALKING' */
  waypoints: Array<{ x: number; z: number }>;
}

export interface OfficeProjectorOptions {
  isDemo: boolean;
  nowMs?: number;
  /**
   * Optional set of agent IDs that have verifiable LIVE coordination/conversation
   * evidence (e.g. active workgroup or conversation participants).
   */
  activeCoordinationAgentIds?: ReadonlySet<string>;
  /**
   * Whether ambient walking animation is allowed for idle connected agents.
   * Defaults to true unless reducedMotion is active.
   */
  ambientWalkEnabled?: boolean;
}

/**
 * Deterministic 32-bit FNV-1a hash from stable agent.id.
 * Ensures workstation assignment and ambient timing depend ONLY on stable agent identity,
 * NEVER on transient LLM model names or execution session IDs.
 */
export function stableAgentHash(agentId: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < agentId.length; i += 1) {
    hash ^= agentId.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

/**
 * Checks whether an assignment has a valid, non-expired active lease.
 * If leaseExpiresAt is present and <= nowMs, the evidence has expired.
 */
export function isAssignmentLeaseValid(
  assignment: AgentIdentity['currentAssignments'][number],
  nowMs: number
): { valid: boolean; expired: boolean } {
  if (assignment.status !== 'ACTIVE' || !assignment.taskId) {
    return { valid: false, expired: false };
  }
  if (assignment.leaseExpiresAt) {
    const expiresMs = Date.parse(assignment.leaseExpiresAt);
    if (Number.isFinite(expiresMs) && expiresMs <= nowMs) {
      return { valid: false, expired: true };
    }
  }
  return { valid: true, expired: false };
}

/**
 * Infers typing specialization strictly from the accredited task/role/capabilities
 * once an active non-expired work assignment is verified.
 */
function inferTypingSpecialization(
  agent: AgentIdentity,
  taskTitle: string
): 'TYPING_DEV' | 'TYPING_AUDIT' | 'TYPING_DOCS' {
  const combined = `${taskTitle} ${agent.roleTitle} ${agent.capabilities
    .map((c) => c.name)
    .join(' ')}`.toLowerCase();

  if (
    combined.includes('audit') ||
    combined.includes('seguridad') ||
    combined.includes('verific') ||
    combined.includes('sast') ||
    combined.includes('atestación') ||
    combined.includes('independencia') ||
    combined.includes('vulnerab')
  ) {
    return 'TYPING_AUDIT';
  }

  if (
    combined.includes('document') ||
    combined.includes('diátaxis') ||
    combined.includes('mandato') ||
    combined.includes('política') ||
    combined.includes('constitucional') ||
    combined.includes('normativ') ||
    combined.includes('especificaci') ||
    combined.includes('adr') ||
    combined.includes('supervisión')
  ) {
    return 'TYPING_DOCS';
  }

  return 'TYPING_DEV';
}

// ============================================================================
// 1. OFFICE ACTIVITY PROJECTOR
// Interprets verifiable operational states without fabricating business activity
// ============================================================================

export function projectAgentOperationalActivity(
  agent: AgentIdentity,
  allAgents: readonly AgentIdentity[],
  options: OfficeProjectorOptions
): ProjectedAgentActivity {
  const nowMs = options.nowMs ?? Date.now();
  const isDemo = options.isDemo || Boolean(agent.isSyntheticDemo);
  const ambientWalkEnabled = options.ambientWalkEnabled ?? true;

  // 1. Disconnected / Offline / Decommissioned -> never simulate activity
  if (
    agent.status === 'OFFLINE' ||
    agent.status === 'DECOMMISSIONED' ||
    agent.heartbeatStatus === 'UNAVAILABLE' ||
    agent.operationalState === 'NO_DISPONIBLE'
  ) {
    return {
      agentId: agent.id,
      kind: 'DISCONNECTED',
      provenance: isDemo ? 'DEMO_SIMULATION' : 'LIVE_VERIFIED_EVIDENCE',
      label: 'Desconectado (Puesto inactivo)',
      shortBadge: '🔌 OFFLINE',
      detail: 'Estado desconectado o sin conexión operativa reportada por el backend.',
      isLeaseExpired: false,
      activeTaskId: null,
      activeProjectId: null,
      conversationPartnerId: null,
    };
  }

  // 2. Evaluate active assignments and check for lease expiration
  let validAssignment: AgentIdentity['currentAssignments'][number] | null = null;
  let hasExpiredLease = false;

  for (const asg of agent.currentAssignments) {
    const check = isAssignmentLeaseValid(asg, nowMs);
    if (check.valid && !validAssignment) {
      validAssignment = asg;
    } else if (check.expired) {
      hasExpiredLease = true;
    }
  }

  // If the only active assignment has an expired lease, fall back to neutral state immediately
  if (!validAssignment && hasExpiredLease) {
    return {
      agentId: agent.id,
      kind: 'UNKNOWN_NEUTRAL',
      provenance: 'NEUTRAL_NO_EVIDENCE',
      label: 'En espera (Evidencia caducada)',
      shortBadge: '⌛ LEASE EXPIRADO',
      detail: 'El lease de la asignación ha caducado; no se representa trabajo activo sin renovación acreditada.',
      isLeaseExpired: true,
      activeTaskId: null,
      activeProjectId: null,
      conversationPartnerId: null,
    };
  }

  // 3. Unknown operational state or unverified assignment vigency -> Neutral representation
  const hasUnknownVigency = agent.currentAssignments.some((a) => a.status === 'UNKNOWN');
  if (
    !validAssignment &&
    (agent.status === 'UNKNOWN' ||
      agent.operationalState === 'DESCONOCIDO' ||
      hasUnknownVigency)
  ) {
    return {
      agentId: agent.id,
      kind: 'UNKNOWN_NEUTRAL',
      provenance: 'NEUTRAL_NO_EVIDENCE',
      label: 'Estado neutral (Sin evidencia activa)',
      shortBadge: '○ NEUTRAL',
      detail: 'Representación neutral en puesto: sin telemetría o vigencia de ejecución acreditada.',
      isLeaseExpired: false,
      activeTaskId: null,
      activeProjectId: null,
      conversationPartnerId: null,
    };
  }

  // 4. Explicit Coordination / Conversation
  // In LIVE: requires explicit activeCoordinationAgentIds evidence (NEVER inferred just from sharing a projectId!).
  // In DEMO: can simulate coordination between available leadership/governance pairs clearly tagged as DEMO_SIMULATION.
  if (options.activeCoordinationAgentIds?.has(agent.id)) {
    const partner = allAgents.find(
      (other) =>
        other.id !== agent.id &&
        options.activeCoordinationAgentIds?.has(other.id) &&
        other.status !== 'OFFLINE'
    );
    if (partner) {
      return {
        agentId: agent.id,
        kind: 'CONVERSING',
        provenance: isDemo ? 'DEMO_SIMULATION' : 'LIVE_VERIFIED_EVIDENCE',
        label: `Conversando con ${partner.name.split(' ')[0]}`,
        shortBadge: '💬 COORD',
        detail: isDemo
          ? `Coordinación simulada en modo DEMO con ${partner.name}.`
          : `Interacción o grupo de trabajo activo acreditado con ${partner.name}.`,
        isLeaseExpired: false,
        activeTaskId: validAssignment?.taskId ?? null,
        activeProjectId: validAssignment?.projectId ?? null,
        conversationPartnerId: partner.id,
      };
    }
  }

  // 5. Verified Active Work -> Typing at Workstation (Developing, Auditing, or Documenting)
  const isActivelyExecuting =
    Boolean(validAssignment) &&
    (agent.status === 'BUSY' ||
      agent.operationalState === 'EJECUTANDO' ||
      Boolean(validAssignment));

  if (isActivelyExecuting && validAssignment) {
    const typingKind = inferTypingSpecialization(agent, validAssignment.taskTitle || '');
    const provenance: ActivityProvenance = isDemo
      ? 'DEMO_SIMULATION'
      : 'LIVE_VERIFIED_EVIDENCE';
    const taskId = validAssignment.taskId ?? null;

    if (typingKind === 'TYPING_AUDIT') {
      return {
        agentId: agent.id,
        kind: 'TYPING_AUDIT',
        provenance,
        label: 'Auditando en su puesto (Tecleando)',
        shortBadge: '🔍 AUDITANDO',
        detail: `${isDemo ? '[DEMO] ' : ''}Trabajo activo acreditado en estación asignada (${taskId || 'activo'}).`,
        isLeaseExpired: false,
        activeTaskId: taskId,
        activeProjectId: validAssignment.projectId,
        conversationPartnerId: null,
      };
    }

    if (typingKind === 'TYPING_DOCS') {
      return {
        agentId: agent.id,
        kind: 'TYPING_DOCS',
        provenance,
        label: 'Documentando / Normativa (Tecleando)',
        shortBadge: '📝 DOCUMENTANDO',
        detail: `${isDemo ? '[DEMO] ' : ''}Trabajo activo acreditado en estación asignada (${taskId || 'activo'}).`,
        isLeaseExpired: false,
        activeTaskId: taskId,
        activeProjectId: validAssignment.projectId,
        conversationPartnerId: null,
      };
    }

    return {
      agentId: agent.id,
      kind: 'TYPING_DEV',
      provenance,
      label: 'Desarrollando en su puesto (Tecleando)',
      shortBadge: '⌨️ DESARROLLANDO',
      detail: `${isDemo ? '[DEMO] ' : ''}Trabajo activo acreditado en estación asignada (${taskId || 'activo'}).`,
      isLeaseExpired: false,
      activeTaskId: taskId,
      activeProjectId: validAssignment.projectId,
      conversationPartnerId: null,
    };
  }

  // 6. Demo-only simulated conversation for idle pairs in the same unit or executive coordination
  if (isDemo && agent.status === 'IDLE' && agent.heartbeatStatus === 'HEALTHY') {
    const idlePeers = allAgents.filter(
      (other) =>
        other.id !== agent.id &&
        (other.isSyntheticDemo || isDemo) &&
        other.status === 'IDLE' &&
        other.heartbeatStatus === 'HEALTHY' &&
        !other.currentAssignments.some((a) => isAssignmentLeaseValid(a, nowMs).valid)
    );
    if (idlePeers.length > 0) {
      const partner = idlePeers[0];
      return {
        agentId: agent.id,
        kind: 'CONVERSING',
        provenance: 'DEMO_SIMULATION',
        label: `Conversando con ${partner.name.split(' ')[0]} (Simulación DEMO)`,
        shortBadge: '💬 DEMO CHAT',
        detail: `Interacción simulada en modo DEMO con ${partner.name}; no representa una conversación real del backend.`,
        isLeaseExpired: false,
        activeTaskId: null,
        activeProjectId: null,
        conversationPartnerId: partner.id,
      };
    }
  }

  // 7. Ambient Walking Animation (explicitly identified as ambient animation, NEVER business evidence)
  if (
    ambientWalkEnabled &&
    agent.status === 'IDLE' &&
    agent.heartbeatStatus === 'HEALTHY'
  ) {
    // Deterministic cycle based on stable hash and time window so idle connected agents occasionally stretch/walk
    const cycleSlot = Math.floor(nowMs / 20_000 + (stableAgentHash(agent.id) % 5)) % 3;
    if (cycleSlot === 1) {
      return {
        agentId: agent.id,
        kind: 'WALKING',
        provenance: isDemo ? 'DEMO_SIMULATION' : 'AMBIENT_ANIMATION',
        label: 'Paseo ambiental por la oficina (Sin acción de negocio)',
        shortBadge: '🚶 AMBIENTAL',
        detail:
          'Animación ambiental de desplazamiento visual para agente disponible; no representa una tarea ni evento empresarial.',
        isLeaseExpired: false,
        activeTaskId: null,
        activeProjectId: null,
        conversationPartnerId: null,
      };
    }
  }

  // 8. Default: Seated & Idle at Assigned Workstation
  return {
    agentId: agent.id,
    kind: 'IDLE_DESK',
    provenance: isDemo ? 'DEMO_SIMULATION' : 'LIVE_VERIFIED_EVIDENCE',
    label: 'Sentado en puesto (Disponible / Inactivo)',
    shortBadge: '🪑 EN PUESTO',
    detail: 'Agente disponible en su estación de trabajo sin ejecución activa acreditada.',
    isLeaseExpired: false,
    activeTaskId: null,
    activeProjectId: null,
    conversationPartnerId: null,
  };
}

// ============================================================================
// 2. OFFICE LIFE ENGINE (Spatial Layout, Stable Workstations & Corridor Routes)
// ============================================================================

/**
 * Builds the physical workstation slots (desk + chair) and meeting zone for a room.
 * Ensures every department visually has real desks, chairs, and a meeting area.
 */
export function buildDepartmentInteriorLayout(room: OfficeRoomConfig): DepartmentInteriorLayout {
  // 4 ergonomic workstation slots arranged in two rows with a clear central walking aisle (x = 0)
  const localConfigs: Array<{ deskX: number; deskZ: number; chairX: number; chairZ: number; facing: number }> = [
    // Front-left workstation (agent sits facing -Z toward monitor)
    { deskX: -1.25, deskZ: -0.95, chairX: -1.25, chairZ: -0.42, facing: Math.PI },
    // Front-right workstation (agent sits facing -Z toward monitor)
    { deskX: 1.25, deskZ: -0.95, chairX: 1.25, chairZ: -0.42, facing: Math.PI },
    // Rear-left workstation (agent sits facing -Z toward monitor)
    { deskX: -1.25, deskZ: 0.35, chairX: -1.25, chairZ: 0.88, facing: Math.PI },
    // Rear-right workstation (agent sits facing -Z toward monitor)
    { deskX: 1.25, deskZ: 0.35, chairX: 1.25, chairZ: 0.88, facing: Math.PI },
  ];

  const workstations: WorkstationSlot[] = localConfigs.map((cfg, idx) => ({
    slotIndex: idx,
    deskLocalX: cfg.deskX,
    deskLocalZ: cfg.deskZ,
    chairLocalX: cfg.chairX,
    chairLocalZ: cfg.chairZ,
    deskWorldX: room.x + cfg.deskX,
    deskWorldZ: room.z + cfg.deskZ,
    chairWorldX: room.x + cfg.chairX,
    chairWorldZ: room.z + cfg.chairZ,
    facingAngle: cfg.facing,
  }));

  // Collaborative meeting table placed near the front-center collaboration nook
  const meetingTableLocal = { x: 0, z: -1.25 };
  const meetingSpots: MeetingSpot[] = [
    {
      spotIndex: 0,
      localX: -0.48,
      localZ: -1.25,
      worldX: room.x - 0.48,
      worldZ: room.z - 1.25,
      facingAngle: Math.PI / 2,
    },
    {
      spotIndex: 1,
      localX: 0.48,
      localZ: -1.25,
      worldX: room.x + 0.48,
      worldZ: room.z - 1.25,
      facingAngle: -Math.PI / 2,
    },
  ];

  // Doorway entry on the side of the room facing the central atrium (0, 0)
  const dirToCenterZ = room.z < 0 ? 1 : -1;
  const corridorEntryWorld = {
    x: room.x,
    z: room.z + dirToCenterZ * (room.depth / 2 - 0.25),
  };

  return {
    roomId: room.id,
    workstations,
    meetingTableLocal,
    meetingSpots,
    corridorEntryWorld,
  };
}

/**
 * Generates an overflow workstation slot around the room perimeter if a department has > 4 agents,
 * guaranteeing zero slot collisions.
 */
function buildOverflowWorkstationSlot(room: OfficeRoomConfig, slotIndex: number): WorkstationSlot {
  const overflowIdx = slotIndex - 4;
  const ring = Math.floor(overflowIdx / 8);
  const radius = 1.65 + ring * 0.55;
  const angle = ((overflowIdx % 8) / 8) * Math.PI * 2;
  const chairLocalX = Math.cos(angle) * radius;
  const chairLocalZ = Math.sin(angle) * radius;
  return {
    slotIndex,
    deskLocalX: chairLocalX,
    deskLocalZ: chairLocalZ - 0.35,
    chairLocalX,
    chairLocalZ,
    deskWorldX: room.x + chairLocalX,
    deskWorldZ: room.z + chairLocalZ - 0.35,
    chairWorldX: room.x + chairLocalX,
    chairWorldZ: room.z + chairLocalZ,
    facingAngle: Math.PI,
  };
}

/**
 * Plans deterministic, collision-free placements and corridor routes for all agents.
 * - Sorts agents within each department by stable `agent.id` so workstation assignment
 *   never changes when LLM model or execution session rotates.
 * - Ensures no two agents ever share the same workstation or meeting spot.
 */
export function planOfficeLifePlacements(
  agents: readonly AgentIdentity[],
  rooms: readonly OfficeRoomConfig[],
  options: OfficeProjectorOptions
): Map<string, PlannedAgentPlacement> {
  const result = new Map<string, PlannedAgentPlacement>();
  const roomLayouts = new Map<string, DepartmentInteriorLayout>();
  for (const room of rooms) {
    roomLayouts.set(room.id, buildDepartmentInteriorLayout(room));
  }

  // Project verifiable activities first
  const projectedById = new Map<string, ProjectedAgentActivity>();
  for (const agent of agents) {
    projectedById.set(
      agent.id,
      projectAgentOperationalActivity(agent, agents, options)
    );
  }

  // Group agents by room and sort deterministically by stable agent.id
  const agentsByRoom = new Map<string, AgentIdentity[]>();
  const unassignedAgents: AgentIdentity[] = [];

  for (const agent of agents) {
    if (roomLayouts.has(agent.unitId)) {
      const list = agentsByRoom.get(agent.unitId) || [];
      list.push(agent);
      agentsByRoom.set(agent.unitId, list);
    } else {
      unassignedAgents.push(agent);
    }
  }

  for (const [roomId, roomAgents] of agentsByRoom.entries()) {
    // Stable sort by agent.id ONLY (immune to LLM model or session changes)
    const stableSorted = [...roomAgents].sort((a, b) => a.id.localeCompare(b.id));
    const room = rooms.find((r) => r.id === roomId)!;
    const layout = roomLayouts.get(roomId)!;

    stableSorted.forEach((agent, stableIndex) => {
      const slot =
        stableIndex < layout.workstations.length
          ? layout.workstations[stableIndex]
          : buildOverflowWorkstationSlot(room, stableIndex);
      const activity = projectedById.get(agent.id)!;

      // Default target is the agent's own workstation chair
      let targetWorldX = slot.chairWorldX;
      let targetWorldZ = slot.chairWorldZ;
      let targetFacingAngle = slot.facingAngle;
      let isSeated =
        activity.kind === 'TYPING_DEV' ||
        activity.kind === 'TYPING_AUDIT' ||
        activity.kind === 'TYPING_DOCS' ||
        activity.kind === 'IDLE_DESK';

      // Build obstacle-free corridor waypoints (Chair -> Central Aisle -> Room Door -> Atrium Ring)
      const aisleWaypoint = { x: room.x, z: slot.chairWorldZ };
      const doorWaypoint = layout.corridorEntryWorld;
      const hashAngle = ((stableAgentHash(agent.id) % 12) / 12) * Math.PI * 2;
      const atriumWaypoint = {
        x: Math.cos(hashAngle) * 2.1,
        z: Math.sin(hashAngle) * 2.1,
      };

      const waypoints = [
        { x: slot.chairWorldX, z: slot.chairWorldZ },
        aisleWaypoint,
        doorWaypoint,
        atriumWaypoint,
        doorWaypoint,
        aisleWaypoint,
      ];

      if (activity.kind === 'WALKING') {
        isSeated = false;
        targetWorldX = doorWaypoint.x;
        targetWorldZ = doorWaypoint.z;
      }

      result.set(agent.id, {
        agentId: agent.id,
        unitId: agent.unitId,
        activity,
        workstationSlot: slot,
        targetWorldX,
        targetWorldZ,
        targetFacingAngle,
        isSeated,
        waypoints,
      });
    });
  }

  // Unassigned agents placed on distinct outer ring spots in the central atrium
  const sortedUnassigned = [...unassignedAgents].sort((a, b) => a.id.localeCompare(b.id));
  sortedUnassigned.forEach((agent, index) => {
    const ring = Math.floor(index / 8);
    const radius = 1.3 + ring * 0.65;
    const countInRing = Math.min(8, sortedUnassigned.length - ring * 8);
    const angle = ((index % 8) / Math.max(1, countInRing)) * Math.PI * 2;
    const worldX = Math.cos(angle) * radius;
    const worldZ = Math.sin(angle) * radius;
    const activity = projectedById.get(agent.id)!;

    const slot: WorkstationSlot = {
      slotIndex: index,
      deskLocalX: worldX,
      deskLocalZ: worldZ - 0.35,
      chairLocalX: worldX,
      chairLocalZ: worldZ,
      deskWorldX: worldX,
      deskWorldZ: worldZ - 0.35,
      chairWorldX: worldX,
      chairWorldZ: worldZ,
      facingAngle: Math.atan2(-worldX, -worldZ),
    };

    result.set(agent.id, {
      agentId: agent.id,
      unitId: agent.unitId,
      activity,
      workstationSlot: slot,
      targetWorldX: worldX,
      targetWorldZ: worldZ,
      targetFacingAngle: slot.facingAngle,
      isSeated: false,
      waypoints: [
        { x: worldX, z: worldZ },
        { x: Math.cos(angle + 0.6) * radius, z: Math.sin(angle + 0.6) * radius },
      ],
    });
  });

  // Resolve CONVERSING pairs so they meet at non-overlapping spots facing each other
  const pairedVisited = new Set<string>();
  let conversationClusterIdx = 0;

  for (const placement of result.values()) {
    if (
      placement.activity.kind !== 'CONVERSING' ||
      !placement.activity.conversationPartnerId ||
      pairedVisited.has(placement.agentId)
    ) {
      continue;
    }

    const partnerPlacement = result.get(placement.activity.conversationPartnerId);
    if (!partnerPlacement) continue;

    pairedVisited.add(placement.agentId);
    pairedVisited.add(partnerPlacement.agentId);

    // If both belong to the same room, use that room's meeting table spots; otherwise meet in the central atrium hub
    const sameRoomLayout =
      placement.unitId === partnerPlacement.unitId
        ? roomLayouts.get(placement.unitId)
        : undefined;

    if (sameRoomLayout && sameRoomLayout.meetingSpots.length >= 2) {
      const spotA = sameRoomLayout.meetingSpots[0];
      const spotB = sameRoomLayout.meetingSpots[1];
      placement.targetWorldX = spotA.worldX;
      placement.targetWorldZ = spotA.worldZ;
      placement.targetFacingAngle = Math.atan2(
        spotB.worldX - spotA.worldX,
        spotB.worldZ - spotA.worldZ
      );
      placement.isSeated = false;

      partnerPlacement.targetWorldX = spotB.worldX;
      partnerPlacement.targetWorldZ = spotB.worldZ;
      partnerPlacement.targetFacingAngle = Math.atan2(
        spotA.worldX - spotB.worldX,
        spotA.worldZ - spotB.worldZ
      );
      partnerPlacement.isSeated = false;
    } else {
      // Distinct conversation spot on the central atrium hub
      const hubAngle = (conversationClusterIdx * Math.PI) / 3 + 0.35;
      conversationClusterIdx += 1;
      const centerX = Math.cos(hubAngle) * 1.65;
      const centerZ = Math.sin(hubAngle) * 1.65;

      const spotAX = centerX - 0.42;
      const spotAZ = centerZ;
      const spotBX = centerX + 0.42;
      const spotBZ = centerZ;

      placement.targetWorldX = spotAX;
      placement.targetWorldZ = spotAZ;
      placement.targetFacingAngle = Math.atan2(spotBX - spotAX, spotBZ - spotAZ);
      placement.isSeated = false;

      partnerPlacement.targetWorldX = spotBX;
      partnerPlacement.targetWorldZ = spotBZ;
      partnerPlacement.targetFacingAngle = Math.atan2(spotAX - spotBX, spotAZ - spotBZ);
      partnerPlacement.isSeated = false;
    }
  }

  return result;
}

/**
 * Computes the interpolated position and facing angle of a walking agent along their
 * obstacle-free corridor waypoints at a given animation timestamp.
 */
export function sampleWaypointRoute(
  waypoints: ReadonlyArray<{ x: number; z: number }>,
  timeMs: number,
  seedOffset = 0
): { x: number; z: number; facingAngle: number; isMoving: boolean } {
  if (waypoints.length === 0) {
    return { x: 0, z: 0, facingAngle: 0, isMoving: false };
  }
  if (waypoints.length === 1) {
    return { x: waypoints[0].x, z: waypoints[0].z, facingAngle: 0, isMoving: false };
  }

  const segmentDurationMs = 3600;
  const pauseDurationMs = 900;
  const stepCycleMs = segmentDurationMs + pauseDurationMs;
  const totalCycleMs = stepCycleMs * waypoints.length;
  const localTime = ((timeMs + seedOffset * 1300) % totalCycleMs + totalCycleMs) % totalCycleMs;

  const segIndex = Math.floor(localTime / stepCycleMs) % waypoints.length;
  const nextIndex = (segIndex + 1) % waypoints.length;
  const inStepTime = localTime - segIndex * stepCycleMs;

  const from = waypoints[segIndex];
  const to = waypoints[nextIndex];
  const dx = to.x - from.x;
  const dz = to.z - from.z;
  const dist = Math.hypot(dx, dz);
  const facingAngle = dist > 0.01 ? Math.atan2(dx, dz) : 0;

  if (inStepTime >= segmentDurationMs || dist < 0.01) {
    return { x: to.x, z: to.z, facingAngle, isMoving: false };
  }

  // Smooth ease-in-out interpolation
  const rawProgress = inStepTime / segmentDurationMs;
  const smoothProgress = rawProgress * rawProgress * (3 - 2 * rawProgress);

  return {
    x: from.x + dx * smoothProgress,
    z: from.z + dz * smoothProgress,
    facingAngle,
    isMoving: true,
  };
}
