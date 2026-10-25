import React, { useState } from 'react';
import type { ProjectBoard, TaskItem, BoardStage, DataState } from '../../domain/models';
import { BOARD_STAGES, BOARD_STAGE_LABELS } from '../../domain/models';
import { Card } from '../../components/ui/Card';
import { SectionHeading, PermissionNotice } from '../../components/ui/SectionHeading';
import { DataStatePanel } from '../../components/ui/DataStatePanel';
import { TaskDetailDrawer } from './TaskDetailDrawer';

export interface KanbanViewProps {
  boardState: DataState<ProjectBoard>;
  selectedProjectId: string | null;
  projectName?: string;
  onRefresh: () => void;
}

export const KanbanView: React.FC<KanbanViewProps> = ({
  boardState,
  selectedProjectId,
  projectName,
  onRefresh,
}) => {
  const [selectedTask, setSelectedTask] = useState<TaskItem | null>(null);

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
          <div
            id="board"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(6, minmax(220px, 1fr))',
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

                  {/* Tasks List */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: 1 }}>
                    {tasks.map((task) => (
                      <div
                        key={task.id}
                        onClick={() => setSelectedTask(task)}
                        style={{
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
                      </div>
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
          </div>
        )}
      />

      <TaskDetailDrawer task={selectedTask} onClose={() => setSelectedTask(null)} />
    </div>
  );
};
