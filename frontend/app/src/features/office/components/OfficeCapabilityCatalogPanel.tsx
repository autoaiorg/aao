import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { AaoReadPort } from '../../../data/ports/AaoReadPort';
import type { CapabilitySummary, DataState, ProjectSummary } from '../../../domain/models';
import { DataStatePanel } from '../../../components/ui/DataStatePanel';
import './office-forms.css';

interface OfficeCapabilityCatalogPanelProps {
  projects: DataState<ProjectSummary[]>;
  port: Pick<AaoReadPort, 'getProjectCapabilities'>;
  sessionId: string;
}

const typeLabel: Record<string, string> = {
  agent_skill: 'Skill de agente',
  knowledge_procedure: 'Procedimiento de conocimiento',
  workflow: 'Workflow',
  cli_script: 'Script CLI',
  library: 'Biblioteca',
  application_service: 'Servicio',
  agent: 'Perfil de agente',
};

export const OfficeCapabilityCatalogPanel: React.FC<OfficeCapabilityCatalogPanelProps> = ({ projects, port, sessionId }) => {
  const activeProjects = useMemo(() => projects.kind === 'ready'
    ? projects.data.filter((project) => (project.status || 'ACTIVE') === 'ACTIVE')
    : [], [projects]);
  const [requestedProjectId, setRequestedProjectId] = useState('');
  const projectId = activeProjects.some((project) => project.id === requestedProjectId)
    ? requestedProjectId : activeProjects[0]?.id || '';
  const capabilitiesQuery = useQuery({
    queryKey: ['office-capability-catalog', sessionId, projectId],
    queryFn: () => port.getProjectCapabilities(projectId),
    enabled: !!projectId,
  });

  return (
    <section className="office-form-panel" aria-labelledby="office-capability-catalog-title">
      <h3 id="office-capability-catalog-title" className="office-form-panel__title">Capacidades registradas</h3>
      <p className="office-form-panel__description">
        Catálogo persistido del proyecto activo: skills, procedimientos y otras capacidades con versión y estado.
        Su registro no concede permisos ni autoriza ejecución; no se infieren asignaciones a agentes.
      </p>
      <label className="office-form-field office-capability-catalog__project">
        Proyecto
        <select className="office-form-control" aria-label="Proyecto del catálogo de capacidades"
          value={projectId} onChange={(event) => setRequestedProjectId(event.target.value)} disabled={!activeProjects.length}>
          {activeProjects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
        </select>
      </label>
      {!projectId && <p role="status">No hay un proyecto activo disponible para consultar capacidades.</p>}
      {capabilitiesQuery.isLoading && <p role="status">Consultando catálogo persistido…</p>}
      {capabilitiesQuery.data && <DataStatePanel state={capabilitiesQuery.data} renderEmpty={() => <p>No hay capacidades registradas en este proyecto.</p>} renderReady={(items: CapabilitySummary[]) => (
        items.length === 0
          ? <p>No hay capacidades registradas en este proyecto.</p>
          : <ul className="office-capability-catalog__list">
            {items.map((item) => (
              <li key={`${item.capability_id}@${item.version}`} className="office-capability-catalog__item">
                <div className="office-capability-catalog__heading">
                  <strong>{item.capability_id}</strong><span>{typeLabel[item.capability_type] ?? item.capability_type}</span>
                </div>
                <p>Versión {item.version} · {item.status}</p>
                <small>Registrada por {item.created_by || 'identidad no informada'} · {Array.isArray(item.evidence) ? item.evidence.length : 0} referencias de evidencia</small>
                <small>Autoriza ejecución: no</small>
              </li>
            ))}
          </ul>
      )} />}
    </section>
  );
};
