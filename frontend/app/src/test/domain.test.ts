import { describe, it, expect } from 'vitest';
import { BOARD_STAGES, BOARD_STAGE_LABELS } from '../domain/models';

describe('Domain Models and Invariants', () => {
  it('preserves exactly the six canonical board lifecycle states in order', () => {
    expect(BOARD_STAGES).toEqual([
      'INBOX',
      'READY',
      'IN_PROGRESS',
      'IN_REVIEW',
      'VERIFIED',
      'DONE',
    ]);
  });

  it('provides correct Spanish labels for all six lifecycle stages', () => {
    expect(BOARD_STAGE_LABELS.INBOX).toBe('Entrada');
    expect(BOARD_STAGE_LABELS.READY).toBe('Preparado');
    expect(BOARD_STAGE_LABELS.IN_PROGRESS).toBe('En curso');
    expect(BOARD_STAGE_LABELS.IN_REVIEW).toBe('Revisión');
    expect(BOARD_STAGE_LABELS.VERIFIED).toBe('Verificado');
    expect(BOARD_STAGE_LABELS.DONE).toBe('Completado');
  });
});
