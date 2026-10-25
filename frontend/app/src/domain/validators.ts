/**
 * Defensive runtime parsers using Zod
 * Ensures HTTP responses adhere strictly to contracts without trusting raw JSON.
 */

import { z } from 'zod';
import type { BoardStage } from './models';

export const BoardStageSchema = z.enum([
  'INBOX',
  'READY',
  'IN_PROGRESS',
  'IN_REVIEW',
  'VERIFIED',
  'DONE',
]);

export const ProjectSummarySchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().optional(),
  state: z.string().optional(),
  status: z.string().optional(),
  mandate_id: z.string().optional(),
});

export const ProjectsListSchema = z.array(ProjectSummarySchema);

export const ExecutionRecordSchema = z.object({
  id: z.string(),
  status: z.string(),
  worker_id: z.string().optional(),
  attempts: z.number().default(0),
  created_at: z.string(),
  result: z.unknown().optional(),
});

export const ReviewRecordSchema = z.object({
  id: z.string(),
  work_id: z.string(),
  reviewer_id: z.string(),
  decision: z.string(),
  candidate_sha: z.string().optional(),
  evidence: z.unknown().optional(),
  created_at: z.string(),
});

export const WorkItemSchema = z.object({
  id: z.string(),
  title: z.string(),
  status: z.string().transform((val): BoardStage => {
    const upper = val.toUpperCase();
    if (['INBOX', 'READY', 'IN_PROGRESS', 'IN_REVIEW', 'VERIFIED', 'DONE'].includes(upper)) {
      return upper as BoardStage;
    }
    return 'INBOX';
  }),
  acceptance_criteria: z.array(z.string()).optional(),
  evidence: z.array(z.unknown()).optional(),
  executions: z.array(ExecutionRecordSchema).optional(),
  author_id: z.string().optional(),
  created_at: z.string().optional(),
});

export const PrincipalSchema = z.object({
  principal_id: z.string(),
  kind: z.enum(['AGENT', 'AUDITOR', 'CEO']),
  enabled: z.boolean(),
});

export const GrantSchema = z.object({
  principal_id: z.string(),
  project_id: z.string(),
  capability: z.string(),
  expires_at: z.string().nullable().optional(),
  active: z.boolean().default(true),
});

export const CapabilitySchema = z.object({
  capability_id: z.string(),
  version: z.string(),
  capability_type: z.string(),
  status: z.string(),
  provenance: z.unknown().optional(),
  contract: z.unknown().optional(),
  required_permissions: z.array(z.string()).optional(),
  risks: z.array(z.string()).optional(),
  dependencies: z.array(z.string()).optional(),
  tests: z.array(z.string()).optional(),
  compatibility: z.array(z.string()).optional(),
  evidence: z.unknown().optional(),
  created_by: z.string().optional(),
  created_at: z.string(),
  execution_authorized: z.boolean().default(false),
});

export const CapabilityEvaluationSchema = z.object({
  task_id: z.string(),
  details: z.unknown().optional(),
  created_at: z.string(),
  task_title: z.string().optional(),
});
