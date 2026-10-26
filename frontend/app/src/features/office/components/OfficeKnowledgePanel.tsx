import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { AaoReadPort } from '../../../data/ports/AaoReadPort';
import type { DataState, KnowledgeSourceRecord, ProjectSummary } from '../../../domain/models';
import { DataStatePanel } from '../../../components/ui/DataStatePanel';
import './office-forms.css';

interface OfficeKnowledgePanelProps {
  projects: DataState<ProjectSummary[]>;
  port: Pick<AaoReadPort, 'getKnowledgeSourceIndex'>;
  sessionId: string;
  onOpenBoard: (projectId: string, workId: string) => void;
}

const navigableEvidenceUrl = (reference: string): string | null => {
  try {
    const url = new URL(reference);
    return url.protocol === 'https:' ? url.href : null;
  } catch {
    return null;
  }
};

/** Read-only index over canonical project work/evidence; this is not a separate knowledge store. */
export const OfficeKnowledgePanel: React.FC<OfficeKnowledgePanelProps> = ({ projects, port, sessionId, onOpenBoard }) => {
  const [search, setSearch] = useState('');
  const indexQuery = useQuery({ queryKey: ['office-corporate-sources', sessionId], queryFn: () => port.getKnowledgeSourceIndex() });
  const projectNames = useMemo(() => new Map(projects.kind === 'ready' ? projects.data.map((project) => [project.id, project.name]) : []), [projects]);
  const records = indexQuery.data?.kind === 'ready' ? indexQuery.data.data : [];
  const filteredRecords = records.filter((record) => `${record.projectName} ${record.title} ${record.status} ${record.workId} ${record.evidenceReferences.join(' ')} ${record.reviews.map((review) => `${review.decision} ${review.reviewerId} ${review.evidenceReferences.join(' ')}`).join(' ')}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));

  return (
    <section className="office-form-panel" aria-labelledby="office-knowledge-title">
      <h3 id="office-knowledge-title" className="office-form-panel__title">Índice corporativo de fuentes</h3>
      <p className="office-form-panel__description">
        Búsqueda de descubrimiento sobre trabajos y revisiones persistidos. No es una base curada y no sustituye las fuentes canónicas.
      </p>
      <label className="office-form-field office-knowledge__project">
        Buscar en fuentes
        <input className="office-form-control" aria-label="Buscar en índice corporativo" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Proyecto, trabajo, estado o referencia" />
      </label>
      {indexQuery.isLoading && <p role="status">Consultando fuentes persistidas…</p>}
      {indexQuery.data && <DataStatePanel state={indexQuery.data} title="Índice corporativo de fuentes"
        onRetry={() => void indexQuery.refetch()} renderEmpty={() => <p>No hay trabajos ni revisiones persistidos en el índice.</p>}
        renderReady={() => filteredRecords.length === 0
          ? <p>{records.length ? 'No hay resultados para la búsqueda.' : 'No hay trabajos ni revisiones persistidos en el índice.'}</p>
          : <ol className="office-knowledge__list" aria-label="Fuentes de trabajo corporativas">
            {filteredRecords.map((item: KnowledgeSourceRecord) => (
              <li className="office-knowledge__item" key={item.workId}>
                <button type="button" className="office-knowledge__link" onClick={() => onOpenBoard(item.projectId, item.workId)}>
                  <strong>{item.title}</strong><span>{item.projectName || projectNames.get(item.projectId) || item.projectId} · Estado: {item.status}</span>
                </button>
                <small>{item.evidenceReferences.length} referencias de trabajo · {item.reviews.length} revisiones · ID {item.workId}</small>
                {[...new Set([...item.evidenceReferences, ...item.reviews.flatMap((review) => review.evidenceReferences)])].length > 0 && <details>
                  <summary>Referencias canónicas ({[...new Set([...item.evidenceReferences, ...item.reviews.flatMap((review) => review.evidenceReferences)])].length})</summary>
                  <ul className="office-knowledge__references">{[...new Set([...item.evidenceReferences, ...item.reviews.flatMap((review) => review.evidenceReferences)])].map((reference) => {
                    const url = navigableEvidenceUrl(reference);
                    return <li key={`${item.workId}-${reference}`}>{url
                      ? <a href={url} target="_blank" rel="noopener noreferrer">{reference}</a>
                      : <code>{reference}</code>}</li>;
                  })}</ul>
                </details>}
                {item.reviews && item.reviews.length > 0 && (
                  <details>
                    <summary>Revisiones registradas ({item.reviews.length})</summary>
                    <ul className="office-knowledge__references">
                      {item.reviews.map((review) => <li key={review.id}>{review.decision} · {review.reviewerId} · {review.createdAt}</li>)}
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
