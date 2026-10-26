import React, { useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { DataState, ProjectSummary } from '../../../domain/models';
import type { AaoConversationPort } from '../../../data/ports/AaoConversationPort';
import { Button } from '../../../components/ui/Button';
import './office-forms.css';

interface OfficeWorkGroupPanelProps {
  projects: DataState<ProjectSummary[]>;
  port: AaoConversationPort;
  sessionId: string;
  onOpenBoard: (projectId: string) => void;
}

export const OfficeWorkGroupPanel: React.FC<OfficeWorkGroupPanelProps> = ({ projects, port, sessionId, onOpenBoard }) => {
  const queryClient = useQueryClient();
  const activeProjects = useMemo(() => projects.kind === 'ready'
    ? projects.data.filter((project) => (project.status || 'ACTIVE') === 'ACTIVE')
    : [], [projects]);
  const [projectId, setProjectId] = useState('');
  const [summaries, setSummaries] = useState<Record<string, string>>({});
  const [pendingGroup, setPendingGroup] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const selectedProjectId = activeProjects.some((project) => project.id === projectId)
    ? projectId : activeProjects[0]?.id || '';
  const groupsQuery = useQuery({
    queryKey: ['office-work-groups', sessionId, selectedProjectId],
    queryFn: () => port.listProjectWorkGroups(selectedProjectId),
    enabled: !!selectedProjectId,
  });
  const agentsQuery = useQuery({
    queryKey: ['office-assignable-agents', sessionId, selectedProjectId],
    queryFn: () => port.listAssignableAgents(selectedProjectId),
    enabled: !!selectedProjectId,
  });
  const groups = groupsQuery.data?.kind === 'ready' ? groupsQuery.data.data : [];
  const agents = agentsQuery.data?.kind === 'ready' ? agentsQuery.data.data : [];
  const [assigneeChoices, setAssigneeChoices] = useState<Record<string, string>>({});

  const assign = async (workId: string, currentPrincipalId: string | null) => {
    const principalId = assigneeChoices[workId] ?? currentPrincipalId ?? '';
    if (!principalId || principalId === currentPrincipalId || pendingGroup) return;
    setPendingGroup(workId);
    setNotice(null);
    const result = await port.assignWorkGroupChild(workId, principalId);
    setPendingGroup(null);
    if (result.kind === 'ready') {
      setNotice(`Trabajo ${workId} asignado a ${result.data.principal_id}. No se han creado grants.`);
      setAssigneeChoices((current) => { const next = { ...current }; delete next[workId]; return next; });
      await queryClient.invalidateQueries({ queryKey: ['office-work-groups', sessionId, selectedProjectId] });
    } else if (result.kind === 'error') {
      setNotice(`${result.code}: ${result.message}`);
      if (result.code === 'HTTP_409') await queryClient.invalidateQueries({ queryKey: ['office-work-groups', sessionId, selectedProjectId] });
    } else if (result.kind === 'forbidden') setNotice(result.reason);
    else setNotice('No se pudo asignar el trabajo.');
  };

  const confirm = async (groupId: string, sourceHash: string) => {
    const summary = summaries[groupId]?.trim();
    if (!selectedProjectId || !summary || pendingGroup) return;
    setPendingGroup(groupId);
    setNotice(null);
    const result = await port.confirmWorkGroupConsolidation(selectedProjectId, groupId, {
      idempotency_key: crypto.randomUUID(), expected_source_sha256: sourceHash, summary,
    });
    setPendingGroup(null);
    if (result.kind === 'ready') {
      setNotice('Consolidación CEO guardada y vinculada al snapshot de trabajos/evidencias. No cambia estados ni inicia ejecuciones.');
      await queryClient.invalidateQueries({ queryKey: ['office-work-groups', sessionId, selectedProjectId] });
    } else if (result.kind === 'error') {
      setNotice(`${result.code}: ${result.message}`);
      if (result.code === 'HTTP_409') {
        await queryClient.invalidateQueries({ queryKey: ['office-work-groups', sessionId, selectedProjectId] });
      }
    } else if (result.kind === 'forbidden') setNotice(result.reason);
    else setNotice('No se pudo confirmar la consolidación.');
  };

  return <section className="office-form-panel" aria-labelledby="office-work-groups-heading">
    <div className="office-form-panel__header">
      <div>
        <h3 id="office-work-groups-heading">Equipos de trabajo y resultados</h3>
        <p>Estado y evidencia desde AAO. La síntesis requiere confirmación explícita del CEO y no admite ni ejecuta tareas.</p>
      </div>
    </div>
    <label className="office-form-field">
      <span>Proyecto</span>
      <select className="office-form-control" value={selectedProjectId} onChange={(event) => setProjectId(event.target.value)} disabled={!activeProjects.length}>
        {activeProjects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
      </select>
    </label>

    {groupsQuery.isLoading && <p role="status">Cargando grupos desde AAO…</p>}
    {groupsQuery.data && groupsQuery.data.kind !== 'ready' && <p role="alert">
      {groupsQuery.data.kind === 'error' ? `${groupsQuery.data.code}: ${groupsQuery.data.message}` : groupsQuery.data.kind === 'forbidden' || groupsQuery.data.kind === 'unavailable' ? groupsQuery.data.reason : 'No hay datos de grupos disponibles.'}
    </p>}
    {groupsQuery.data?.kind === 'ready' && groups.length === 0 && <p>No hay grupos persistidos en este proyecto.</p>}
    {groups.map((group) => <article className="office-work-group" key={group.id}>
      <header className="office-work-group__header">
        <div><h4>{group.title}</h4><p>Padre {group.parent_status} · {group.children.length} trabajos hijos · fuente {group.source_sha256.slice(0, 12)}</p></div>
        <Button type="button" variant="secondary" onClick={() => onOpenBoard(selectedProjectId)}>Abrir tablero</Button>
      </header>
      <ul className="office-work-group__children">
        {group.children.map((child) => {
          const currentAssignment = agents.find((agent) => agent.principal_id === child.assigned_principal_id);
          const hasActiveExecution = child.executions.some((execution) => ['QUEUED', 'RUNNING', 'UNCERTAIN'].includes(execution.status));
          const assignmentLocked = ['IN_REVIEW', 'VERIFIED', 'DONE'].includes(child.status) || hasActiveExecution;
          const selectedAssignee = assigneeChoices[child.work_id] ?? child.assigned_principal_id ?? '';
          const canSaveAssignment = !!selectedAssignee && selectedAssignee !== child.assigned_principal_id && !assignmentLocked;
          return <li key={child.work_id} className="office-work-group__child">
            <span>{child.work_id}</span><strong>{child.status}</strong>
            <span>{child.executions.length} ejecuciones · {child.reviews.length} revisiones · {Array.isArray(child.evidence) ? child.evidence.length : child.evidence ? 1 : 0} evidencias</span>
            <span>Responsable: {currentAssignment?.display_name || child.assigned_principal_id || 'Sin asignar'}</span>
            {!group.consolidation && <div className="office-work-group__assignment">
              <label className="office-form-field">
                <span>{child.assigned_principal_id ? 'Cambiar responsable' : 'Asignar responsable'}</span>
                <select className="office-form-control" value={selectedAssignee} disabled={assignmentLocked || pendingGroup === child.work_id || agentsQuery.isLoading || agents.length === 0} onChange={(event) => setAssigneeChoices((current) => ({ ...current, [child.work_id]: event.target.value }))}>
                  <option value="">Seleccionar identidad autorizada</option>
                  {agents.map((agent) => <option key={agent.principal_id} value={agent.principal_id}>{agent.display_name} ({agent.principal_id})</option>)}
                </select>
              </label>
              <Button type="button" variant="secondary" disabled={!canSaveAssignment || pendingGroup === child.work_id} onClick={() => void assign(child.work_id, child.assigned_principal_id)}>
                {pendingGroup === child.work_id ? 'Guardando…' : child.assigned_principal_id ? 'Cambiar asignación' : 'Asignar'}
              </Button>
            </div>}
          </li>;
        })}
      </ul>
      {group.consolidation ? <div className="office-work-group__saved">
        <strong>Consolidación guardada · {group.consolidation.created_by}</strong>
        <p>{group.consolidation.summary}</p>
        <small>Snapshot {group.consolidation.source_sha256.slice(0, 16)} · {new Date(group.consolidation.created_at).toLocaleString()}</small>
      </div> : <form onSubmit={(event) => { event.preventDefault(); void confirm(group.id, group.source_sha256); }}>
        <label className="office-form-field">
          <span>Síntesis CEO (persistente)</span>
          <textarea className="office-form-control office-form-control--textarea" rows={3} maxLength={20000} required value={summaries[group.id] || ''} onChange={(event) => setSummaries((current) => ({ ...current, [group.id]: event.target.value }))} disabled={!group.consolidation_ready || pendingGroup === group.id} placeholder={group.consolidation_ready ? 'Resume los resultados revisados…' : 'Disponible cuando todos los trabajos hijos estén DONE.'} />
        </label>
        <Button type="submit" disabled={!group.consolidation_ready || !summaries[group.id]?.trim() || pendingGroup === group.id}>
          {pendingGroup === group.id ? 'Guardando…' : 'Confirmar consolidación'}
        </Button>
      </form>}
    </article>)}
    {notice && <p role="status">{notice}</p>}
  </section>;
};
