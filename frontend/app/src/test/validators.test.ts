import { describe, it, expect } from 'vitest';
import {
  ProjectsListSchema,
  PrincipalSchema,
  WorkItemSchema,
  CapabilitySchema,
  CapabilityEvaluationSchema,
} from '../domain/validators';

describe('Defensive Schema Validation', () => {
  it('validates valid projects array correctly', () => {
    const raw = [
      { id: 'proj-1', name: 'Alpha Project', state: 'ACTIVE' },
      { id: 'proj-2', name: 'Beta Project', description: 'Test project' },
    ];
    const parsed = ProjectsListSchema.safeParse(raw);
    expect(parsed.success).toBe(true);
    if (parsed.success) {
      expect(parsed.data).toHaveLength(2);
      expect(parsed.data[0].name).toBe('Alpha Project');
    }
  });

  it('rejects corrupted projects array', () => {
    const raw = [{ invalid_field: 123 }];
    const parsed = ProjectsListSchema.safeParse(raw);
    expect(parsed.success).toBe(false);
  });

  it('validates principal credentials response', () => {
    const raw = {
      principal_id: 'agent-1234',
      kind: 'AGENT',
      enabled: true,
    };
    const parsed = PrincipalSchema.safeParse(raw);
    expect(parsed.success).toBe(true);
    if (parsed.success) {
      expect(parsed.data.kind).toBe('AGENT');
    }
  });

  it('normalizes work item lifecycle status to canonical uppercase', () => {
    const raw = {
      id: 'task-01',
      title: 'Fix issue',
      status: 'in_review',
    };
    const parsed = WorkItemSchema.safeParse(raw);
    expect(parsed.success).toBe(true);
    if (parsed.success) {
      expect(parsed.data.status).toBe('IN_REVIEW');
    }
  });

  it('defaults invalid work item status to INBOX safely', () => {
    const raw = {
      id: 'task-02',
      title: 'Unrecognized stage',
      status: 'UNKNOWN_CUSTOM_STAGE',
    };
    const parsed = WorkItemSchema.safeParse(raw);
    expect(parsed.success).toBe(true);
    if (parsed.success) {
      expect(parsed.data.status).toBe('INBOX');
    }
  });

  it('validates capability versions and enforces execution_authorized is false by default', () => {
    const raw = {
      capability_id: 'tool-test',
      version: '1.0.0',
      capability_type: 'agent_skill',
      status: 'ACTIVE',
      created_at: '2026-10-25T00:00:00Z',
    };
    const parsed = CapabilitySchema.safeParse(raw);
    expect(parsed.success).toBe(true);
    if (parsed.success) {
      expect(parsed.data.execution_authorized).toBe(false);
    }
  });

  it('validates capability evaluations record', () => {
    const raw = {
      task_id: 'task-100',
      details: { check: 'passed' },
      created_at: '2026-10-25T08:00:00Z',
      task_title: 'Evaluation Task',
    };
    const parsed = CapabilityEvaluationSchema.safeParse(raw);
    expect(parsed.success).toBe(true);
  });
});
