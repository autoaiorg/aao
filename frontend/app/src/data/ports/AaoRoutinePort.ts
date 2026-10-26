import type { DataState } from '../../domain/models';

export interface RoutineInput {
  idempotency_key: string;
  title: string;
  description: string;
  acceptance_criteria: string[];
  interval_seconds: number;
  first_run_at: string;
}

export interface ProjectRoutine {
  id: string;
  template: Pick<RoutineInput, 'title' | 'description' | 'acceptance_criteria'>;
  interval_seconds: number;
  next_run_at: string;
  enabled: boolean;
  authorized_by: string;
  created_at: string;
  execution_authorized: false;
}

/** Durable INBOX templates. Enabling a routine never authorizes execution. */
export interface AaoRoutinePort {
  listRoutines(projectId: string): Promise<DataState<ProjectRoutine[]>>;
  createRoutine(projectId: string, input: RoutineInput): Promise<DataState<{ id: string; created: boolean }>>;
  setRoutineEnabled(projectId: string, routineId: string, enabled: boolean): Promise<DataState<{ id: string; enabled: boolean }>>;
}
