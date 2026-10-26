import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { AaoReadPort } from '../../../data/ports/AaoReadPort';
import type { DataState, ProjectSummary, TaskItem } from '../../../domain/models';
import { Button } from '../../../components/ui/Button';
import './office-forms.css';

interface OfficeCalendarPanelProps {
  projects: DataState<ProjectSummary[]>;
  port: Pick<AaoReadPort, 'getProjectBoard'>;
  sessionId: string;
  onOpenWork: (projectId: string, workId?: string) => void;
}

const localDate = () => {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
};

export const OfficeCalendarPanel: React.FC<OfficeCalendarPanelProps> = ({ projects, port, sessionId, onOpenWork }) => {
  const activeProjects = useMemo(() => projects.kind === 'ready'
    ? projects.data.filter((project) => (project.status || 'ACTIVE') === 'ACTIVE')
    : [], [projects]);
  const [requestedProjectId, setRequestedProjectId] = useState('');
  const projectId = activeProjects.some((project) => project.id === requestedProjectId)
    ? requestedProjectId : activeProjects[0]?.id || '';
  const boardQuery = useQuery({
    queryKey: ['office-dated-work', sessionId, projectId],
    queryFn: () => port.getProjectBoard(projectId),
    enabled: !!projectId,
  });
  const today = localDate();

  return (
    <section className="office-form-panel" aria-labelledby="office-calendar-title">
      <div className="office-form-panel__header">
        <div>
          <h3 id="office-calendar-title" className="office-form-panel__title">Fechas objetivo</h3>
          <p className="office-form-panel__description">Vista LIVE de fechas persistidas en los trabajos canónicos del proyecto. No programa ni inicia ejecuciones.</p>
        </div>
        {projectId && <Button type="button" variant="secondary" onClick={() => onOpenWork(projectId)}>Abrir tablero</Button>}
      </div>
      <label className="office-form-field office-calendar__project">Proyecto
        <select className="office-form-control" aria-label="Proyecto del calendario" value={projectId}
          onChange={(event) => setRequestedProjectId(event.target.value)} disabled={!activeProjects.length}>
          {activeProjects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
        </select>
      </label>
      {projects.kind !== 'ready' && <p role="alert">No se pueden cargar proyectos: {projects.kind === 'error' ? projects.message : projects.kind === 'forbidden' ? projects.reason : projects.kind === 'unavailable' ? projects.reason : 'datos no disponibles'}.</p>}
      {projects.kind === 'ready' && !projectId && <p role="status">No hay proyectos activos con acceso para mostrar fechas.</p>}
      {projectId && boardQuery.isLoading && <p role="status">Consultando trabajos persistidos…</p>}
      {projectId && boardQuery.data?.kind === 'error' && <p role="alert">{boardQuery.data.code}: {boardQuery.data.message}</p>}
      {projectId && boardQuery.data?.kind === 'forbidden' && <p role="alert">{boardQuery.data.reason}</p>}
      {projectId && boardQuery.data?.kind === 'unavailable' && <p role="alert">{boardQuery.data.reason}</p>}
      {projectId && boardQuery.data?.kind === 'ready' && (() => {
        const datedItems = boardQuery.data.data.items
          .filter((item): item is TaskItem & { dueDate: string } => Boolean(item.dueDate))
          .sort((a, b) => a.dueDate.localeCompare(b.dueDate) || a.title.localeCompare(b.title));
        return datedItems.length === 0
          ? <p role="status">No hay trabajos con fecha objetivo registrada en este proyecto.</p>
          : <ol className="office-calendar__list" aria-label="Trabajos con fecha objetivo">
            {datedItems.map((item) => (
              <li key={item.id}>
                <button type="button" className="office-calendar__item" onClick={() => onOpenWork(projectId, item.id)}>
                  <time dateTime={item.dueDate}>{new Date(`${item.dueDate}T00:00:00`).toLocaleDateString('es-ES', { dateStyle: 'medium' })}</time>
                  <span className="office-calendar__item-title">{item.title}</span>
                  <span className="office-calendar__status">{item.status}</span>
                  {item.dueDate < today && item.status !== 'DONE' && <span className="office-calendar__overdue">Vencida</span>}
                </button>
              </li>
            ))}
          </ol>;
      })()}
      {projectId && boardQuery.data?.kind === 'empty' && <p role="status">El tablero está vacío; no hay fechas objetivo registradas.</p>}
    </section>
  );
};
