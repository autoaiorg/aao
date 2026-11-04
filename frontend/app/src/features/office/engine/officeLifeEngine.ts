import type { AgentIdentity } from '../../../domain/models';
import type { OfficeLabelLodTier, OfficeRoomConfig } from '../types';
import { planWorkNeighborhoodDesks } from '../spatialPlanningEngine';

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

  if (agent.credentialStatus === 'DISABLED' && !validAssignment) {
    return {
      agentId: agent.id,
      kind: 'DISCONNECTED',
      provenance: isDemo ? 'DEMO_SIMULATION' : 'LIVE_VERIFIED_EVIDENCE',
      label: 'Identidad deshabilitada (sin puesto activo)',
      shortBadge: '🔌 INACTIVO',
      detail: 'Identidad deshabilitada sin tarea vigente; no se representa como agente activo ni ocupa un escritorio departamental.',
      isLeaseExpired: hasExpiredLease,
      activeTaskId: null,
      activeProjectId: null,
      conversationPartnerId: null,
    };
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
  // A missing capacity is a legacy rendering contract (e.g. static OFFICE_ROOMS fixtures).
  // Data-driven LIVE/DEMO layouts always set an exact observed count, including zero.
  const capacity = Math.max(0, room.workstationCapacity ?? 4);
  const localConfigs = planWorkNeighborhoodDesks(capacity, room.id).map(({ x, z }) => ({
    deskX: x,
    deskZ: z,
    chairX: x,
    chairZ: z + 0.55,
    facing: Math.PI,
  }));

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
    const hasActiveDeskTask = agent.currentAssignments.some(
      (assignment) => assignment.status === 'ACTIVE' && Boolean(assignment.taskId),
    );
    if (roomLayouts.has(agent.unitId) &&
        (agent.credentialStatus !== 'DISABLED' || hasActiveDeskTask)) {
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
      const walkSide = stableAgentHash(agent.id) % 2 === 0 ? -1 : 1;
      const neighborhoodWaypoint = {
        x: room.x + walkSide * (room.width / 2 + 0.75),
        z: doorWaypoint.z,
      };

      const waypoints = [
        { x: slot.chairWorldX, z: slot.chairWorldZ },
        aisleWaypoint,
        doorWaypoint,
        neighborhoodWaypoint,
        doorWaypoint,
        aisleWaypoint,
      ].filter((point, index, all) => index === 0 ||
        Math.hypot(point.x - all[index - 1].x, point.z - all[index - 1].z) > 0.01);

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

  // Unassigned agents remain in a neutral holding area near the campus origin;
  // no organizational unit is inferred for them.
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

    // Conversations use a local standing pair in a real team neighborhood,
    // never a fabricated radial gathering around the origin.
    const conversationRoomId = [placement.unitId, partnerPlacement.unitId].sort()[0];
    const conversationRoom = rooms.find((room) => room.id === conversationRoomId);
    const baseX = conversationRoom?.x ?? (placement.workstationSlot.chairWorldX + partnerPlacement.workstationSlot.chairWorldX) / 2;
    const baseZ = conversationRoom?.z ?? (placement.workstationSlot.chairWorldZ + partnerPlacement.workstationSlot.chairWorldZ) / 2;
    const offset = 0.48 + (conversationClusterIdx % 3) * 0.24;
    conversationClusterIdx += 1;
    const spotAX = baseX - offset;
    const spotBX = baseX + offset;

    placement.targetWorldX = spotAX;
    placement.targetWorldZ = baseZ + 0.15;
    placement.targetFacingAngle = Math.PI / 2;
    placement.isSeated = false;
    partnerPlacement.targetWorldX = spotBX;
    partnerPlacement.targetWorldZ = baseZ + 0.15;
    partnerPlacement.targetFacingAngle = -Math.PI / 2;
    partnerPlacement.isSeated = false;
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

// ============================================================================
// 3. ADAPTIVE LABEL LOD & SCREEN-SPACE DE-OVERLAPPING ENGINE (Phase 3 - P0)
// ============================================================================

export interface AdaptiveDepartmentLabelState {
  roomId: string;
  visible: boolean;
  lodTier: OfficeLabelLodTier;
  abbreviated: boolean;
  scale: number;
  yOffset: number;
}

export interface AdaptiveAgentLabelState {
  agentId: string;
  visible: boolean;
  lodTier: OfficeLabelLodTier;
  priority: number;
  scale: number;
  yOffset: number;
  offsetX: number;
  offsetZ: number;
  suppressedByOverlap: boolean;
  provenanceCode: 'LIVE' | 'DEMO' | 'AMBIENT' | 'UNKNOWN';
}

export interface AdaptiveLabelsResult {
  lodTier: OfficeLabelLodTier;
  departments: Map<string, AdaptiveDepartmentLabelState>;
  agents: Map<string, AdaptiveAgentLabelState>;
  visibleDepartmentCount: number;
  visibleAgentCount: number;
  suppressedOverlapCount: number;
}

/**
 * Determines the current semantic Level of Detail (LOD) tier from camera distance:
 * - 'overview'   (distance >= 18): Department abbreviated headers + critical/selected agent only.
 * - 'department' (11.5 <= distance < 18): Department full header + primary agents in focused sector.
 * - 'agent'      (distance < 11.5): Full agent badge with operational status and provenance.
 */
export function deriveLabelLodTier(cameraDistance: number): OfficeLabelLodTier {
  if (cameraDistance >= 18) return 'overview';
  if (cameraDistance >= 11.5) return 'department';
  return 'agent';
}

/**
 * Computes contextual label visibility, scale, vertical de-overlapping offsets, and density limits
 * so labels never collide into an unreadable pile.
 */
export function computeAdaptiveLabelStates(params: {
  rooms: readonly OfficeRoomConfig[];
  agents: readonly AgentIdentity[];
  placements: ReadonlyMap<string, { x: number; z: number; activity: ProjectedAgentActivity }>;
  cameraDistance: number;
  cameraAngleDeg: number;
  cameraTargetX: number;
  cameraTargetZ: number;
  selectedRoomId: string | null;
  selectedAgentId: string | null;
}): AdaptiveLabelsResult {
  const {
    rooms,
    agents,
    placements,
    cameraDistance,
    cameraAngleDeg,
    cameraTargetX,
    cameraTargetZ,
    selectedRoomId,
    selectedAgentId,
  } = params;

  const lodTier = deriveLabelLodTier(cameraDistance);
  const departments = new Map<string, AdaptiveDepartmentLabelState>();
  const agentStates = new Map<string, AdaptiveAgentLabelState>();

  let visibleDepartmentCount = 0;
  for (const room of rooms) {
    const isSelected = room.id === selectedRoomId;
    const roomDistance = Math.hypot(room.x - cameraTargetX, room.z - cameraTargetZ);
    // Keep distant room headers out of focused views; room geometry remains selectable.
    const visible = lodTier !== 'agent' && (
      lodTier === 'overview' ||
      isSelected ||
      roomDistance <= 8
    );
    const scale =
      lodTier === 'overview'
        ? isSelected
          ? 0.92
          : 0.76
        : lodTier === 'department'
        ? isSelected
          ? 0.92
          : 0.76
        : 0.78;
    departments.set(room.id, {
      roomId: room.id,
      visible,
      lodTier,
      abbreviated: lodTier === 'overview' && !isSelected,
      scale,
      yOffset: isSelected ? 2.45 : 2.32,
    });
    if (visible) visibleDepartmentCount += 1;
  }

  // Project 3D world (x, z) onto camera horizontal axis for 2D overlap detection
  const rad = (cameraAngleDeg * Math.PI) / 180;
  const cosA = Math.cos(rad);
  const sinA = Math.sin(rad);
  const projectToScreenPlane = (wx: number, wz: number, wy: number) => {
    const dx = wx - cameraTargetX;
    const dz = wz - cameraTargetZ;
    const screenX = dx * cosA - dz * sinA;
    const depthZ = dx * sinA + dz * cosA;
    const screenY = wy - depthZ * 0.42;
    return { screenX, screenY };
  };

  interface CandidateAgent {
    agent: AgentIdentity;
    pos: { x: number; z: number };
    activity: ProjectedAgentActivity;
    priority: number;
    provenanceCode: 'LIVE' | 'DEMO' | 'AMBIENT' | 'UNKNOWN';
    eligibleByLod: boolean;
  }

  const candidates: CandidateAgent[] = [];

  for (const agent of agents) {
    const placement = placements.get(agent.id);
    if (!placement) continue;

    const isSelected = agent.id === selectedAgentId;
    const hasCriticalAlert = Boolean(
      agent.executionHistory?.some(
        (ex) => ex.isBudgetExceeded || ex.isNoProgressRetry || Boolean(ex.alert)
      )
    );
    const isInSelectedRoom = Boolean(selectedRoomId && agent.unitId === selectedRoomId);
    const distToCameraTarget = Math.hypot(
      placement.x - cameraTargetX,
      placement.z - cameraTargetZ
    );
    const isExecuting =
      placement.activity.kind === 'TYPING_DEV' ||
      placement.activity.kind === 'TYPING_AUDIT' ||
      placement.activity.kind === 'TYPING_DOCS' ||
      placement.activity.kind === 'CONVERSING';

    let priority = 50;
    if (isSelected) priority = 1000;
    else if (hasCriticalAlert) priority = 850;
    else if (isInSelectedRoom && isExecuting) priority = 500;
    else if (isInSelectedRoom) priority = 350;
    else if (isExecuting) priority = 220;
    else if (agent.status === 'IDLE') priority = 110;

    const prov = placement.activity.provenance;
    const provenanceCode: CandidateAgent['provenanceCode'] =
      prov === 'LIVE_VERIFIED_EVIDENCE'
        ? 'LIVE'
        : prov === 'DEMO_SIMULATION'
        ? 'DEMO'
        : prov === 'AMBIENT_ANIMATION'
        ? 'AMBIENT'
        : 'UNKNOWN';

    // Determine base LOD eligibility:
    // - Overview: ONLY selected agent or critical alert agents show individual name labels!
    // - Department: Agents in selected room or within 6.2u of camera target.
    // - Agent closeup: Agents within 8.5u of camera target or in selected room.
    let eligibleByLod = false;
    if (lodTier === 'overview') {
      eligibleByLod = isSelected || hasCriticalAlert;
    } else if (lodTier === 'department') {
      eligibleByLod = isSelected || hasCriticalAlert || isInSelectedRoom || distToCameraTarget <= 6.2;
    } else {
      eligibleByLod = isSelected || hasCriticalAlert || distToCameraTarget <= 4.5;
    }

    candidates.push({
      agent,
      pos: { x: placement.x, z: placement.z },
      activity: placement.activity,
      priority,
      provenanceCode,
      eligibleByLod,
    });
  }

  // Sort by priority descending, then deterministic agent.id tie-breaker
  candidates.sort((a, b) => {
    if (b.priority !== a.priority) return b.priority - a.priority;
    return a.agent.id.localeCompare(b.agent.id);
  });

  const acceptedBoxes: Array<{ screenX: number; screenY: number }> = [];
  // A label sprite is roughly 1.6 world units wide. Give each accepted label
  // at least its own footprint, then shift colliding labels sideways in the
  // camera plane before lifting them above heads and monitors.
  const minSepX = 1.85;
  const minSepY = 0.56;
  const maxVisibleAgentLabels = lodTier === 'overview' ? 3 : lodTier === 'department' ? 8 : 1;

  let visibleAgentCount = 0;
  let suppressedOverlapCount = 0;

  for (const cand of candidates) {
    const isMustShow = cand.priority >= 800; // selected or critical alert
    if (!cand.eligibleByLod) {
      agentStates.set(cand.agent.id, {
        agentId: cand.agent.id,
        visible: false,
        lodTier,
        priority: cand.priority,
        scale: 0.85,
        yOffset: 1.24,
        offsetX: 0,
        offsetZ: 0,
        suppressedByOverlap: false,
        provenanceCode: cand.provenanceCode,
      });
      continue;
    }

    if (!isMustShow && visibleAgentCount >= maxVisibleAgentLabels) {
      suppressedOverlapCount += 1;
      agentStates.set(cand.agent.id, {
        agentId: cand.agent.id,
        visible: false,
        lodTier,
        priority: cand.priority,
        scale: 0.85,
        yOffset: 1.24,
        offsetX: 0,
        offsetZ: 0,
        suppressedByOverlap: true,
        provenanceCode: cand.provenanceCode,
      });
      continue;
    }

    let baseWy = 1.24;
    let offsetX = 0;
    let offsetZ = 0;
    let proj = projectToScreenPlane(cand.pos.x, cand.pos.z, baseWy);
    const collides = (sx: number, sy: number) =>
      acceptedBoxes.some(
        (box) => Math.abs(box.screenX - sx) < minSepX && Math.abs(box.screenY - sy) < minSepY
      );

    let hasOverlap = collides(proj.screenX, proj.screenY);
    if (hasOverlap) {
      const lateralOffsets = [0, -1.9, 1.9, -3.8, 3.8, -5.7, 5.7];
      const verticalOffsets = [1.24, 1.62, 1.98];
      for (const yOffset of verticalOffsets) {
        let placed = false;
        for (const screenOffset of lateralOffsets) {
          const candidateX = screenOffset * cosA;
          const candidateZ = -screenOffset * sinA;
          const candidateProjection = projectToScreenPlane(
            cand.pos.x + candidateX,
            cand.pos.z + candidateZ,
            yOffset,
          );
          if (collides(candidateProjection.screenX, candidateProjection.screenY)) continue;
          baseWy = yOffset;
          offsetX = candidateX;
          offsetZ = candidateZ;
          proj = candidateProjection;
          hasOverlap = false;
          placed = true;
          break;
        }
        if (placed) break;
      }
    }

    if (hasOverlap && !isMustShow) {
      suppressedOverlapCount += 1;
      agentStates.set(cand.agent.id, {
        agentId: cand.agent.id,
        visible: false,
        lodTier,
        priority: cand.priority,
        scale: 0.85,
        yOffset: 1.24,
        offsetX: 0,
        offsetZ: 0,
        suppressedByOverlap: true,
        provenanceCode: cand.provenanceCode,
      });
      continue;
    }

    acceptedBoxes.push(proj);
    visibleAgentCount += 1;
    const scale =
      cand.priority >= 1000
        ? lodTier === 'agent' ? 0.48 : 1.12
        : lodTier === 'agent'
        ? 0.48
        : lodTier === 'department'
        ? 0.92
        : 0.88;

    agentStates.set(cand.agent.id, {
      agentId: cand.agent.id,
      visible: true,
      lodTier,
      priority: cand.priority,
      scale,
      yOffset: baseWy,
      offsetX,
      offsetZ,
      suppressedByOverlap: false,
      provenanceCode: cand.provenanceCode,
    });
  }

  return {
    lodTier,
    departments,
    agents: agentStates,
    visibleDepartmentCount,
    visibleAgentCount,
    suppressedOverlapCount,
  };
}
