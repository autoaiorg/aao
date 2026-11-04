import type {
  AlertSummary,
  DataState,
  DecisionSummary,
  OrganizationStructure,
  ProjectSummary,
} from '../../domain/models';
import type { CEOWorkRequest, CreatedWorkRequest } from '../../data/ports/AaoWorkCommandPort';
import type { AaoConversationPort } from '../../data/ports/AaoConversationPort';
import type { AaoReadPort } from '../../data/ports/AaoReadPort';
import type { AaoCapabilityFeedbackPort } from '../../data/ports/AaoCapabilityFeedbackPort';
import type {
  OrganizationProfileCommand,
  OrganizationUnitCommand,
} from '../../data/ports/AaoOrganizationCommandPort';

import type { AaoRoutinePort } from '../../data/ports/AaoRoutinePort';

export type OfficeViewMode = '3d' | '2d';
export type OfficeLayoutMode = 'hud' | 'classic';
export type OfficeCameraPreset = 'overview' | 'isometric' | 'top-down' | 'agent-focus';
export type OfficeBottomDeckState = 'minimized' | 'docked' | 'maximized';
export type OfficeGraphicsQuality = 'low' | 'balanced' | 'high';
export type OfficeLabelLodTier = 'overview' | 'department' | 'agent';
export type OfficeHudTabId =
  | 'work-request'
  | 'comms'
  | 'activity'
  | 'work-groups'
  | 'capabilities'
  | 'routines'
  | 'calendar'
  | 'knowledge';

export interface CameraViewState {
  angle: number;
  elevation: number;
  distance: number;
  targetX: number;
  targetZ: number;
  lodTier?: OfficeLabelLodTier;
  followAgentId?: string | null;
}

export interface OfficeScenePerfMetrics {
  qualityProfile: OfficeGraphicsQuality;
  fpsEstimate: number;
  lastFrameTimeMs: number;
  lastStateUpdateMs: number;
  interactiveMeshesCount: number;
  roomsCount: number;
  agentsCount: number;
  visibleDepartmentLabelsCount: number;
  visibleAgentLabelsCount: number;
  suppressedOverlapLabelsCount: number;
  sharedGeometriesCount: number;
  sharedMaterialsCount: number;
}

export type OperationalStateCategory =
  | 'ACTIVO'
  | 'INACTIVO'
  | 'BLOQUEADO'
  | 'PENDIENTE'
  | 'DESCONOCIDO'
  | 'DESCONECTADO'
  | 'HISTORICO';

export type OfficeZoneKind =
  | 'canonical-department'
  | 'unassigned-holding'
  | 'executive-suite'
  | 'audit-enclave'
  | 'agile-squad-pod'
  | 'onboarding-lobby';

export type OfficeFloorFinish =
  | 'acoustic-carpet'
  | 'hardwood-walnut'
  | 'polished-terrazzo'
  | 'high-security-frosted';

export interface OfficeDoorwayPortal {
  x: number;
  z: number;
  width: number;
  facingAngle: number;
}

export interface OfficeGlassWallSegment {
  startX: number;
  startZ: number;
  endX: number;
  endZ: number;
  height: number;
  hasManifestationBand?: boolean;
}

export interface OfficeRoomConfig {
  id: string;
  code: string;
  name: string;
  x: number;
  z: number;
  width: number;
  depth: number;
  color: string;
  accentColor: string;
  kind?: OfficeZoneKind;
  floorFinish?: OfficeFloorFinish;
  doorway?: OfficeDoorwayPortal;
  glassWalls?: OfficeGlassWallSegment[];
  parentId?: string | null;
  workstationCapacity?: number;
}

export const OFFICE_ROOMS: OfficeRoomConfig[] = [
  {
    id: 'unit-exec',
    code: 'EXEC',
    name: 'Dirección Ejecutiva',
    x: -6,
    z: -4,
    width: 4.8,
    depth: 4.2,
    color: '#1e3a8a',
    accentColor: '#3b82f6',
    kind: 'executive-suite',
    floorFinish: 'hardwood-walnut',
  },
  {
    id: 'unit-gov',
    code: 'GOV',
    name: 'Gobernanza y Políticas',
    x: 0,
    z: -4,
    width: 4.8,
    depth: 4.2,
    color: '#4c1d95',
    accentColor: '#8b5cf6',
    kind: 'canonical-department',
    floorFinish: 'acoustic-carpet',
  },
  {
    id: 'unit-audit',
    code: 'AUDIT',
    name: 'Auditoría Independiente',
    x: 6,
    z: -4,
    width: 4.8,
    depth: 4.2,
    color: '#064e3b',
    accentColor: '#10b981',
    kind: 'audit-enclave',
    floorFinish: 'high-security-frosted',
  },
  {
    id: 'unit-arch',
    code: 'ARCH',
    name: 'Arquitectura de Sistemas',
    x: -6,
    z: 4,
    width: 4.8,
    depth: 4.2,
    color: '#78350f',
    accentColor: '#f59e0b',
    kind: 'canonical-department',
    floorFinish: 'acoustic-carpet',
  },
  {
    id: 'unit-eng',
    code: 'ENG',
    name: 'Ingeniería e Implementación',
    x: 0,
    z: 4,
    width: 4.8,
    depth: 4.2,
    color: '#164e63',
    accentColor: '#06b6d4',
    kind: 'canonical-department',
    floorFinish: 'acoustic-carpet',
  },
  {
    id: 'unit-ops',
    code: 'OPS',
    name: 'Operaciones e Infraestructura',
    x: 6,
    z: 4,
    width: 4.8,
    depth: 4.2,
    color: '#713f12',
    accentColor: '#d97706',
    kind: 'canonical-department',
    floorFinish: 'acoustic-carpet',
  },
];

export interface VirtualOfficeViewProps {
  organization: DataState<OrganizationStructure>;
  projects?: DataState<ProjectSummary[]>;
  alertsState?: DataState<AlertSummary[]>;
  decisionsState?: DataState<DecisionSummary[]>;
  canCreateWorkRequest?: boolean;
  conversationPort?: AaoConversationPort;
  workGroupPort?: AaoConversationPort;
  isCeoSession?: boolean;
  capabilityReadPort?: Pick<AaoReadPort, 'getProjectCapabilities'>;
  capabilityFeedbackPort?: AaoCapabilityFeedbackPort;
  activityReadPort?: Pick<AaoReadPort, 'getProjectActivity'>;
  knowledgeReadPort?: Pick<AaoReadPort, 'getKnowledgeSourceIndex'>;
  routinePort?: AaoRoutinePort;
  calendarReadPort?: Pick<AaoReadPort, 'getProjectBoard'>;
  conversationSessionId?: string;
  canManageOrganization?: boolean;
  onSaveUnit?: (input: OrganizationUnitCommand) => Promise<DataState<unknown>>;
  onSaveProfile?: (input: OrganizationProfileCommand) => Promise<DataState<unknown>>;
  onCreateWorkRequest?: (projectId: string, input: CEOWorkRequest) => Promise<DataState<CreatedWorkRequest>>;
  onNavigate?: (
    target: 'organization' | 'kanban' | 'projects' | 'decisions' | 'alerts' | 'audit',
    projectId?: string,
    workId?: string
  ) => void;
  onRefresh?: () => void;
}

export interface OfficeInteractionState {
  selectedRoomId: string;
  selectedAgentId: string | null;
  viewMode: OfficeViewMode;
  searchQuery: string;
  typeFilter: 'ALL' | 'STANDING' | 'EPHEMERAL';
  reducedMotion: boolean;
}
