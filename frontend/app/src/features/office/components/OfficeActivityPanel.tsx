import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { AaoReadPort } from '../../../data/ports/AaoReadPort';
import type { ActivityEvent, DataState, ProjectSummary } from '../../../domain/models';
import { Button } from '../../../components/ui/Button';
import { DataStatePanel } from '../../../components/ui/DataStatePanel';
import './office-forms.css';

interface OfficeActivityPanelProps {
  projects: DataState<ProjectSummary[]>;
  port: Pick<AaoReadPort, 'getProjectActivity'>;
  sessionId: string;
  onOpenBoard: (projectId: string, workId?: string) => void;
}

function describeActivity(event: ActivityEvent): string {
  if (event.kind === 'work.dispatch_blocked') return 'Bloqueo de despacho';
  if (event.kind.startsWith('execution.')) return 'Ejecución';
  if (event.kind.startsWith('work.')) return 'Trabajo';
  if (event.kind.startsWith('review.')) return 'Revisión';
  if (event.kind.startsWith('conversation.')) return 'Conversación';
  return 'Evento persistido';
}

function dispatchBlockerReason(event: ActivityEvent): string | undefined {
  if (event.kind !== 'work.dispatch_blocked' || !event.details || typeof event.details !== 'object') {
    return undefined;
  }
  const reason = (event.details as Record<string, unknown>).reason;
  return typeof reason === 'string' && reason.trim() ? reason.trim() : undefined;
}

export const OfficeActivityPanel: React.FC<OfficeActivityPanelProps> = ({ projects, port, sessionId, onOpenBoard }) => {
  const activeProjects = useMemo(() => projects.kind === 'ready'
    ? projects.data.filter((project) => (project.status || 'ACTIVE') === 'ACTIVE')
    : [], [projects]);
  const [requestedProjectId, setRequestedProjectId] = useState('');
  const projectId = activeProjects.some((project) => project.id === requestedProjectId)
    ? requestedProjectId : activeProjects[0]?.id || '';
  const activityQuery = useQuery({
    queryKey: ['office-project-activity', sessionId, projectId],
    queryFn: () => port.getProjectActivity(projectId),
    enabled: !!projectId,
  });

  return (
    <section className="office-form-panel" aria-labelledby="office-activity-title">
      <div className="office-form-panel__header">
        <div>
          <h3 id="office-activity-title" className="office-form-panel__title">Actividad registrada</h3>
          <p className="office-form-panel__description">
            Eventos y journal persistidos por AAO, no una señal de presencia del agente. Usa «Abrir tablero» para consultar el trabajo asociado.
          </p>
        </div>
        {projectId && <Button type="button" variant="secondary" onClick={() => onOpenBoard(projectId)}>Abrir tablero</Button>}
      </div>
      <label className="office-form-field office-activity__project">
        Proyecto
        <select className="office-form-control" aria-label="Proyecto de actividad"
          value={projectId} onChange={(event) => setRequestedProjectId(event.target.value)} disabled={!activeProjects.length}>
          {activeProjects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
        </select>
      </label>
      {!projectId && <p role="status">No hay un proyecto activo disponible para consultar actividad.</p>}
      {activityQuery.isLoading && <p role="status">Consultando eventos de AAO…</p>}
      {activityQuery.data && <DataStatePanel state={activityQuery.data} title="Actividad del proyecto"
        onRetry={() => void activityQuery.refetch()} renderEmpty={() => <p>No hay actividad registrada en este proyecto.</p>}
        renderReady={(events: ActivityEvent[]) => events.length === 0
          ? <p>No hay actividad registrada en este proyecto.</p>
          : <ol className="office-activity__list" aria-label="Actividad persistida del proyecto">
            {events.slice(0, 20).map((event) => (
              <li key={event.id}>
                <button type="button" className="office-activity__event" onClick={() => onOpenBoard(projectId, event.kind.startsWith('work.') ? event.subject_id : undefined)}>
                  <span className="office-activity__kind">{describeActivity(event)} · {event.kind}</span>
                  {dispatchBlockerReason(event) && <span className="office-activity__reason">{dispatchBlockerReason(event)}</span>}
                  <code>{event.subject_id}</code>
                  <time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString('es-ES')}</time>
                </button>
              </li>
            ))}
          </ol>
        } />}
    </section>
  );
};
