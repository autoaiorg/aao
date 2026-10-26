import type { DataState, OrganizationStructure, ProjectSummary } from '../../domain/models';
import type { CEOWorkRequest, CreatedWorkRequest } from '../../data/ports/AaoWorkCommandPort';
import type { AaoConversationPort } from '../../data/ports/AaoConversationPort';
import type { AaoReadPort } from '../../data/ports/AaoReadPort';
import type { AaoCapabilityFeedbackPort } from '../../data/ports/AaoCapabilityFeedbackPort';

export type OfficeViewMode = '3d' | '2d';

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
  },
];

export interface VirtualOfficeViewProps {
  organization: DataState<OrganizationStructure>;
  projects?: DataState<ProjectSummary[]>;
  canCreateWorkRequest?: boolean;
  conversationPort?: AaoConversationPort;
  capabilityReadPort?: Pick<AaoReadPort, 'getProjectCapabilities'>;
  capabilityFeedbackPort?: AaoCapabilityFeedbackPort;
  activityReadPort?: Pick<AaoReadPort, 'getProjectActivity'>;
  knowledgeReadPort?: Pick<AaoReadPort, 'getKnowledgeSourceIndex'>;
  calendarReadPort?: Pick<AaoReadPort, 'getProjectBoard'>;
  conversationSessionId?: string;
  onCreateWorkRequest?: (projectId: string, input: CEOWorkRequest) => Promise<DataState<CreatedWorkRequest>>;
  onNavigate?: (target: 'organization' | 'kanban' | 'projects', projectId?: string, workId?: string) => void;
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
