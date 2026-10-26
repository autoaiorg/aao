import type { DataState } from '../../domain/models';

export interface OrganizationUnitCommand {
  id: string;
  name: string;
  code: string;
  parent_id: string | null;
  lead_principal_id: string | null;
  enabled: boolean;
}

export interface OrganizationProfileCommand {
  principal_id: string;
  display_name: string;
  role_title: string;
  unit_id: string | null;
  manager_principal_id: string | null;
  competencies?: string[];
  enabled: boolean;
}

export interface AaoOrganizationCommandPort {
  putOrganizationUnit(input: OrganizationUnitCommand): Promise<DataState<unknown>>;
  putOrganizationProfile(input: OrganizationProfileCommand): Promise<DataState<unknown>>;
}
