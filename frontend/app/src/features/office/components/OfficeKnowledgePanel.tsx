import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { AaoReadPort } from '../../../data/ports/AaoReadPort';
import type { DataState, ProjectBoard, ProjectSummary, TaskItem } from '../../../domain/models';
import { DataStatePanel } from '../../../components/ui/DataStatePanel';
import './office-forms.css';

function evidenceReferences(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((reference): reference is string => typeof reference === 'string' && reference.trim().length > 0)
    : [];
}

interface OfficeKnowledgePanelProps {
  projects: DataState<ProjectSummary[]>;
  port: Pick<AaoReadPort, 'getProjectBoard'>;
  sessionId: string;
  onOpenBoard: (projectId: string, workId: string) => void;
}

/** Read-only index over canonical project work/evidence; this is not a separate knowledge store. */
export const OfficeKnowledgePanel: React.FC<OfficeKnowledgePanelProps> = ({ projects, port, sessionId, onOpenBoard }) => {
  const activeProjects = useMemo(() => projects.kind === 'ready'
    ? projects.data.filter((project) => (project.status || 'ACTIVE') === 'ACTIVE')
    : [], [projects]);
  const [requestedProjectId, setRequestedProjectId] = useState('');
  const projectId = activeProjects.some((project) => project.id === requestedProjectId)
    ? requestedProjectId : activeProjects[0]?.id || '';
  const boardQuery = useQuery({
    queryKey: ['office-project-knowledge', sessionId, projectId],
    queryFn: () => port.getProjectBoard(projectId),
    enabled: !!projectId,
  });

  return (
    <section className="office-form-panel" aria-labelledby="office-knowledge-title">
      <h3 id="office-knowledge-title" className="office-form-panel__title">Conocimiento y evidencia del proyecto</h3>
      <p className="office-form-panel__description">
        Índice de lectura de trabajos y evidencias ya persistidos en AAO. No crea conocimiento nuevo ni sustituye sus fuentes canónicas.
      </p>
      <label className="office-form-field office-knowledge__project">
        Proyecto
        <select className="office-form-control" aria-label="Proyecto del índice de conocimiento"
          value={projectId} onChange={(event) => setRequestedProjectId(event.target.value)} disabled={!activeProjects.length}>
          {activeProjects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
        </select>
      </label>
      {!projectId && <p role="status">No hay un proyecto activo disponible para consultar.</p>}
      {boardQuery.isLoading && <p role="status">Consultando registros persistidos…</p>}
      {boardQuery.data && <DataStatePanel state={boardQuery.data} title="Índice de conocimiento"
        onRetry={() => void boardQuery.refetch()} renderEmpty={() => <p>No hay trabajos ni evidencias en este proyecto.</p>}
        renderReady={(board: ProjectBoard) => board.items.length === 0
          ? <p>No hay trabajos ni evidencias en este proyecto.</p>
          : <ol className="office-knowledge__list" aria-label="Registros de trabajo del proyecto">
            {board.items.map((item: TaskItem) => (
              <li className="office-knowledge__item" key={item.id}>
                <button type="button" className="office-knowledge__link" onClick={() => onOpenBoard(projectId, item.id)}>
                  <strong>{item.title}</strong><span>Estado: {item.status || 'desconocido'}</span>
                </button>
                <small>
                  {item.evidence?.length ?? 0} referencias de evidencia · {item.executions?.length ?? 0} ejecuciones · {item.reviews?.length ?? 0} revisiones
                </small>
                {item.acceptanceCriteria && item.acceptanceCriteria.length > 0 && (
                  <details>
                    <summary>Criterios de aceptación ({item.acceptanceCriteria.length})</summary>
                    <ul>{item.acceptanceCriteria.map((criterion, index) => <li key={`${item.id}-criterion-${index}`}>{criterion}</li>)}</ul>
                  </details>
                )}
                {(() => {
                  const references = [...new Set([
                    ...evidenceReferences(item.evidence),
                    ...(item.reviews ?? []).flatMap((review) => evidenceReferences(review.evidence)),
                  ])];
                  return references.length > 0 ? (
                    <details>
                      <summary>Referencias canónicas ({references.length})</summary>
                      <ul className="office-knowledge__references">
                        {references.map((reference) => <li key={`${item.id}-${reference}`}><code>{reference}</code></li>)}
                      </ul>
                    </details>
                  ) : null;
                })()}
                {item.reviews && item.reviews.length > 0 && (
                  <details>
                    <summary>Revisiones registradas ({item.reviews.length})</summary>
                    <ul className="office-knowledge__references">
                      {item.reviews.map((review) => <li key={review.id}>{review.decision} · {review.reviewer_id} · {review.created_at}</li>)}
                    </ul>
                  </details>
                )}
              </li>
            ))}
          </ol>}
      />}
    </section>
  );
};
