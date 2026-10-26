import React, { useEffect, useState } from 'react';
import type { ProjectBoard, TaskItem, BoardStage, DataState } from '../../domain/models';
import { BOARD_STAGES, BOARD_STAGE_LABELS } from '../../domain/models';
import { Card } from '../../components/ui/Card';
import { SectionHeading, PermissionNotice } from '../../components/ui/SectionHeading';
import { DataStatePanel } from '../../components/ui/DataStatePanel';
import { TaskDetailDrawer } from './TaskDetailDrawer';
import type { WorkPriority } from '../../data/ports/AaoWorkCommandPort';

export interface KanbanViewProps {
  boardState: DataState<ProjectBoard>;
  selectedProjectId: string | null;
  projectName?: string;
  onRefresh: () => void;
  focusWorkId?: string | null;
  onFocusWorkConsumed?: () => void;
  canManagePriority?: boolean;
  onSetPriority?: (workId: string, priority: WorkPriority) => Promise<DataState<unknown>>;
}

export const KanbanView: React.FC<KanbanViewProps> = ({
  boardState,
  selectedProjectId,
  projectName,
  onRefresh,
  focusWorkId,
  onFocusWorkConsumed,
  canManagePriority = false,
  onSetPriority,
}) => {
  const [selectedTask, setSelectedTask] = useState<TaskItem | null>(null);

  useEffect(() => {
    if (!focusWorkId || boardState.kind !== 'ready') return;
    const tasks = [...Object.values(boardState.data.stages).flat(), ...(boardState.data.unrecognizedItems || [])];
    const task = tasks.find((item) => item.id === focusWorkId);
    if (task) setSelectedTask(task);
    onFocusWorkConsumed?.();
  }, [focusWorkId, boardState, onFocusWorkConsumed]);

  useEffect(() => {
    if (!selectedTask || boardState.kind !== 'ready') return;
    const current = boardState.data.items.find((item) => item.id === selectedTask.id);
    if (current && current !== selectedTask) setSelectedTask(current);
  }, [boardState, selectedTask]);

  const stageBorderColors: Record<BoardStage, string> = {
    INBOX: 'var(--stage-inbox)',
    READY: 'var(--stage-ready)',
    IN_PROGRESS: 'var(--stage-in-progress)',
    IN_REVIEW: 'var(--stage-in-review)',
    VERIFIED: 'var(--stage-verified)',
    DONE: 'var(--stage-done)',
  };

  if (!selectedProjectId) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        <SectionHeading
          title="Tablero de Trabajo (Kanban)"
          subtitle="Ciclo de vida operativo en seis estados canónicos"
        />
        <Card elevation="none" style={{ textAlign: 'center', padding: '48px 24px' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '8px' }}>
            Seleccione un proyecto específico
          </h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: '13px', maxWidth: '480px', margin: '0 auto' }}>
            El tablero Kanban opera a nivel de proyecto conforme al contrato de AAO. Utilice el selector de proyectos en la cabecera superior o la vista de Cartera para ver las tareas.
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div>
        <SectionHeading
          title={`Tablero: ${projectName || selectedProjectId}`}
          subtitle="Visualización en solo lectura de las tareas del proyecto y sus seis estados canónicos"
        />
        <PermissionNotice message="El tablero observa el estado real de trabajo en el núcleo. La reasignación o cambio de estado de tareas requiere autorización de ejecución en backend." />
      </div>

      <DataStatePanel
        state={boardState}
        onRetry={onRefresh}
        title="Tablero de Trabajo"
        renderReady={(board) => (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* Warning banner if any tasks have unrecognized non-canonical states */}
            {board.unrecognizedItems && board.unrecognizedItems.length > 0 && (
              <div
                role="alert"
                style={{
                  padding: '12px 16px',
                  borderRadius: 'var(--radius-md)',
                  backgroundColor: 'var(--status-warning-bg)',
                  border: '1px solid var(--status-warning-border)',
                  color: 'var(--status-warning-text)',
                  fontSize: '13px',
                }}
              >
                <strong>Atención:</strong> Se detectaron {board.unrecognizedItems.length} tarea(s) con estados no reconocidos en el ciclo canónico. Se presentan con su estado semántico original sin conversión forzada a INBOX.
              </div>
            )}

            <div
              id="board"
              style={{
                display: 'grid',
                gridTemplateColumns: `repeat(${BOARD_STAGES.length + (board.unrecognizedItems?.length ? 1 : 0)}, minmax(220px, 1fr))`,
                gap: '12px',
                overflowX: 'auto',
                paddingBottom: '16px',
              }}
            >
              {BOARD_STAGES.map((stage) => {
                const tasks = board.stages[stage] || [];
                return (
                  <div
                    key={stage}
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      backgroundColor: 'var(--bg-muted)',
                      borderRadius: 'var(--radius-lg)',
                      padding: '12px',
                      minHeight: '480px',
                      borderTop: `4px solid ${stageBorderColors[stage]}`,
                    }}
                  >
                    {/* Column Header */}
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginBottom: '12px',
                        paddingBottom: '8px',
                        borderBottom: '1px solid var(--border-subtle)',
                      }}
                    >
                      <span style={{ fontWeight: 700, fontSize: '13px', color: 'var(--text-primary)' }}>
                        {BOARD_STAGE_LABELS[stage]}
                      </span>
                      <span
                        style={{
                          fontSize: '11px',
                          padding: '1px 6px',
                          borderRadius: 'var(--radius-full)',
                          backgroundColor: 'var(--bg-surface)',
                          fontWeight: 700,
                          color: 'var(--text-secondary)',
                        }}
                      >
                        {tasks.length}
                      </span>
                    </div>

                    {/* Tasks List with keyboard-accessible semantic buttons */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: 1 }}>
                      {tasks.map((task) => (
                        <button
                          key={task.id}
                          type="button"
                          onClick={() => setSelectedTask(task)}
                          aria-haspopup="dialog"
                          aria-label={`Ver detalles de la tarea ${task.id}: ${task.title}`}
                          style={{
                            width: '100%',
                            textAlign: 'left',
                            backgroundColor: 'var(--bg-surface)',
                            borderRadius: 'var(--radius-md)',
                            padding: '10px 12px',
                            border: '1px solid var(--border-subtle)',
                            boxShadow: 'var(--shadow-sm)',
                            cursor: 'pointer',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '6px',
                            transition: 'border-color 0.15s ease',
                            fontFamily: 'inherit',
                          }}
                        >
                          <span
                            style={{
                              fontSize: '11px',
                              fontFamily: 'monospace',
                              color: 'var(--text-muted)',
                            }}
                          >
                            {task.id}
                          </span>
                          <strong
                            style={{
                              fontSize: '13px',
                              fontWeight: 600,
                              color: 'var(--text-primary)',
                              lineHeight: 1.3,
                            }}
                          >
                            {task.title}
                          </strong>

                          {task.executions && task.executions.length > 0 && (
                            <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                              ⚙ {task.executions.length} ejecución(es)
                            </div>
                          )}
                          {task.reviews && task.reviews.length > 0 && (
                            <div style={{ fontSize: '11px', color: 'var(--accent)' }}>
                              ✓ {task.reviews.length} revisión(es)
                            </div>
                          )}
                        </button>
                      ))}

                      {tasks.length === 0 && (
                        <div
                          style={{
                            textAlign: 'center',
                            padding: '24px 8px',
                            color: 'var(--text-muted)',
                            fontSize: '12px',
                            fontStyle: 'italic',
                          }}
                        >
                          Sin tareas en {BOARD_STAGE_LABELS[stage].toLowerCase()}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}

              {/* Dedicated column for Unrecognized/Non-canonical states */}
              {board.unrecognizedItems && board.unrecognizedItems.length > 0 && (
                <div
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    backgroundColor: 'var(--status-warning-bg)',
                    borderRadius: 'var(--radius-lg)',
                    padding: '12px',
                    minHeight: '480px',
                    borderTop: '4px solid var(--status-warning-border)',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginBottom: '12px',
                      paddingBottom: '8px',
                      borderBottom: '1px solid var(--status-warning-border)',
                    }}
                  >
                    <span style={{ fontWeight: 700, fontSize: '13px', color: 'var(--status-warning-text)' }}>
                      Estado No Reconocido
                    </span>
                    <span
                      style={{
                        fontSize: '11px',
                        padding: '1px 6px',
                        borderRadius: 'var(--radius-full)',
                        backgroundColor: 'var(--bg-surface)',
                        fontWeight: 700,
                        color: 'var(--status-warning-text)',
                      }}
                    >
                      {board.unrecognizedItems.length}
                    </span>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: 1 }}>
                    {board.unrecognizedItems.map((task) => (
                      <button
                        key={task.id}
                        type="button"
                        onClick={() => setSelectedTask(task)}
                        aria-haspopup="dialog"
                        aria-label={`Ver detalles de la tarea con estado no reconocido ${task.id}: ${task.title}`}
                        style={{
                          width: '100%',
                          textAlign: 'left',
                          backgroundColor: 'var(--bg-surface)',
                          borderRadius: 'var(--radius-md)',
                          padding: '10px 12px',
                          border: '1px solid var(--status-warning-border)',
                          boxShadow: 'var(--shadow-sm)',
                          cursor: 'pointer',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '6px',
                          fontFamily: 'inherit',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontSize: '11px', fontFamily: 'monospace', color: 'var(--text-muted)' }}>
                            {task.id}
                          </span>
                          <span
                            style={{
                              fontSize: '10px',
                              padding: '1px 5px',
                              borderRadius: 'var(--radius-sm)',
                              backgroundColor: 'var(--status-warning-bg)',
                              color: 'var(--status-warning-text)',
                              fontWeight: 700,
                            }}
                          >
                            {task.status || 'SIN_ESTADO'}
                          </span>
                        </div>
                        <strong
                          style={{
                            fontSize: '13px',
                            fontWeight: 600,
                            color: 'var(--text-primary)',
                            lineHeight: 1.3,
                          }}
                        >
                          {task.title}
                        </strong>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      />

      <TaskDetailDrawer task={selectedTask} onClose={() => setSelectedTask(null)}
        canManagePriority={canManagePriority} onSetPriority={onSetPriority} />
    </div>
  );
};
