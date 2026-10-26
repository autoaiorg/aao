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

const dateKey = (year: number, month: number, day: number) =>
  `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;

export const OfficeCalendarPanel: React.FC<OfficeCalendarPanelProps> = ({ projects, port, sessionId, onOpenWork }) => {
  const activeProjects = useMemo(() => projects.kind === 'ready'
    ? projects.data.filter((project) => (project.status || 'ACTIVE') === 'ACTIVE')
    : [], [projects]);
  const [requestedProjectId, setRequestedProjectId] = useState('');
  const [displayedMonth, setDisplayedMonth] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });
  const projectId = activeProjects.some((project) => project.id === requestedProjectId)
    ? requestedProjectId : activeProjects[0]?.id || '';
  const boardQuery = useQuery({
    queryKey: ['office-dated-work', sessionId, projectId],
    queryFn: () => port.getProjectBoard(projectId),
    enabled: !!projectId,
    refetchInterval: 15_000,
  });
  const today = localDate();

  return (
    <section className="office-form-panel" aria-labelledby="office-calendar-title">
      <div className="office-form-panel__header">
        <div>
          <h3 id="office-calendar-title" className="office-form-panel__title">Fechas objetivo</h3>
          <p className="office-form-panel__description">Vista LIVE de fechas persistidas en los trabajos canónicos del proyecto; se actualiza cada 15 segundos mientras está abierta. No programa ni inicia ejecuciones.</p>
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
        const year = displayedMonth.getFullYear();
        const month = displayedMonth.getMonth();
        const monthLabel = displayedMonth.toLocaleDateString('es-ES', { month: 'long', year: 'numeric' });
        const firstWeekday = (new Date(year, month, 1).getDay() + 6) % 7;
        const dayCount = new Date(year, month + 1, 0).getDate();
        const cellCount = Math.ceil((firstWeekday + dayCount) / 7) * 7;
        const byDate = new Map<string, typeof datedItems>();
        for (const item of datedItems) byDate.set(item.dueDate, [...(byDate.get(item.dueDate) || []), item]);
        return <>
          <div className="office-calendar__month-nav" aria-label="Navegación del calendario">
            <Button type="button" variant="secondary" onClick={() => setDisplayedMonth(new Date(year, month - 1, 1))}>Mes anterior</Button>
            <h4 aria-live="polite">{monthLabel}</h4>
            <Button type="button" variant="secondary" onClick={() => setDisplayedMonth(new Date(year, month + 1, 1))}>Mes siguiente</Button>
            <Button type="button" variant="secondary" onClick={() => {
              const now = new Date();
              setDisplayedMonth(new Date(now.getFullYear(), now.getMonth(), 1));
            }}>Este mes</Button>
          </div>
          {datedItems.length === 0
            ? <p role="status">No hay trabajos con fecha objetivo registrada en este proyecto.</p>
            : <div className="office-calendar__grid-wrap"><table className="office-calendar__grid" aria-label={`Calendario de ${monthLabel}`}>
              <thead><tr>{['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'].map((day) => <th key={day} scope="col">{day}</th>)}</tr></thead>
              <tbody>{Array.from({ length: cellCount / 7 }, (_, week) => <tr key={week}>
                {Array.from({ length: 7 }, (_, weekday) => {
                  const day = week * 7 + weekday - firstWeekday + 1;
                  if (day < 1 || day > dayCount) return <td key={weekday} className="office-calendar__outside" aria-hidden="true" />;
                  const key = dateKey(year, month, day);
                  const dayItems = byDate.get(key) || [];
                  return <td key={weekday}>
                    <time className="office-calendar__day" dateTime={key}>{day}</time>
                    <ul>{dayItems.map((item) => <li key={item.id}>
                      <button type="button" className="office-calendar__work" onClick={() => onOpenWork(projectId, item.id)}>
                        <span className="office-calendar__item-title">{item.title}</span>
                        <span className="office-calendar__status">{item.status}</span>
                        {item.dueDate < today && item.status !== 'DONE' && <span className="office-calendar__overdue">Vencida</span>}
                      </button>
                    </li>)}</ul>
                  </td>;
                })}
              </tr>)}</tbody>
            </table></div>}
          {datedItems.length > 0 && !datedItems.some((item) => item.dueDate.startsWith(`${year}-${String(month + 1).padStart(2, '0')}-`))
            && <p role="status">No hay trabajos con fecha objetivo en este mes.</p>}
        </>;
      })()}
      {projectId && boardQuery.data?.kind === 'empty' && <p role="status">El tablero está vacío; no hay fechas objetivo registradas.</p>}
    </section>
  );
};
