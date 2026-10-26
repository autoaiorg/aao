import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { AaoReadPort } from '../../../data/ports/AaoReadPort';
import type { AaoCapabilityFeedbackPort, CapabilityFeedbackVersionInput } from '../../../data/ports/AaoCapabilityFeedbackPort';
import type { CapabilitySummary, DataState, ProjectSummary } from '../../../domain/models';
import { DataStatePanel } from '../../../components/ui/DataStatePanel';
import './office-forms.css';

interface OfficeCapabilityCatalogPanelProps {
  projects: DataState<ProjectSummary[]>;
  port: Pick<AaoReadPort, 'getProjectCapabilities'>;
  feedbackPort?: AaoCapabilityFeedbackPort;
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

export const OfficeCapabilityCatalogPanel: React.FC<OfficeCapabilityCatalogPanelProps> = ({ projects, port, feedbackPort, sessionId }) => {
  const activeProjects = useMemo(() => projects.kind === 'ready'
    ? projects.data.filter((project) => (project.status || 'ACTIVE') === 'ACTIVE')
    : [], [projects]);
  const [requestedProjectId, setRequestedProjectId] = useState('');
  const [correction, setCorrection] = useState('');
  const [evidenceText, setEvidenceText] = useState('');
  const [workId, setWorkId] = useState('');
  const [selectedCapability, setSelectedCapability] = useState('');
  const [submitState, setSubmitState] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [reviewState, setReviewState] = useState<string | null>(null);
  const [versionDraftId, setVersionDraftId] = useState<string | null>(null);
  const [versionDraft, setVersionDraft] = useState<CapabilityFeedbackVersionInput | null>(null);
  const [versionContractText, setVersionContractText] = useState('');
  const [versionTestsText, setVersionTestsText] = useState('');
  const [versionEvidenceText, setVersionEvidenceText] = useState('');
  const [versionState, setVersionState] = useState<string | null>(null);
  const projectId = activeProjects.some((project) => project.id === requestedProjectId)
    ? requestedProjectId : activeProjects[0]?.id || '';
  const capabilitiesQuery = useQuery({
    queryKey: ['office-capability-catalog', sessionId, projectId],
    queryFn: () => port.getProjectCapabilities(projectId),
    enabled: !!projectId,
  });
  const feedbackQuery = useQuery({
    queryKey: ['office-capability-feedback', sessionId, projectId],
    queryFn: () => feedbackPort!.listCapabilityFeedback(projectId),
    enabled: !!projectId && !!feedbackPort,
  });
  const capabilities = capabilitiesQuery.data?.kind === 'ready' ? capabilitiesQuery.data.data : [];
  const selected = capabilities.find((item) => `${item.capability_id}@${item.version}` === selectedCapability) ?? capabilities[0];
  const selectedValue = selected ? `${selected.capability_id}@${selected.version}` : '';
  const submitFeedback = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!feedbackPort || !projectId || !selected || !correction.trim()) return;
    const evidence = evidenceText.split('\n').map((value) => value.trim()).filter(Boolean);
    if (evidence.length === 0 && !workId.trim()) {
      setSubmitState('Añade una referencia de evidencia o el ID de un trabajo canónico.');
      return;
    }
    setSubmitting(true);
    const result = await feedbackPort.proposeCapabilityFeedback(projectId, {
      capability_id: selected.capability_id, version: selected.version, correction: correction.trim(),
      work_id: workId.trim() || null, evidence,
    });
    setSubmitting(false);
    if (result.kind === 'ready') {
      setCorrection('');
      setEvidenceText('');
      setWorkId('');
      setSubmitState('Propuesta persistida; no se ha aplicado a la skill ni al catálogo.');
      await feedbackQuery.refetch();
    } else {
      setSubmitState(result.kind === 'error' ? `${result.code}: ${result.message}`
        : result.kind === 'forbidden' ? result.reason : 'No se pudo guardar la propuesta.');
    }
  };

  const reviewFeedback = async (proposalId: string, status: 'accepted' | 'rejected') => {
    if (!feedbackPort) return;
    setReviewingId(proposalId);
    setReviewState(null);
    const result = await feedbackPort.reviewCapabilityFeedback(projectId, proposalId, status);
    setReviewingId(null);
    if (result.kind === 'ready') {
      setReviewState(status === 'accepted' ? 'Propuesta aceptada; no aplicada a ninguna capacidad.' : 'Propuesta rechazada; no aplicada a ninguna capacidad.');
      await feedbackQuery.refetch();
    } else {
      setReviewState(result.kind === 'error' ? `${result.code}: ${result.message}`
        : result.kind === 'forbidden' ? result.reason : 'No se pudo guardar la revisión.');
      await feedbackQuery.refetch();
    }
  };

  const beginVersionDraft = (proposalId: string, capabilityId: string, sourceVersion: string) => {
    const source = capabilities.find((item) => item.capability_id === capabilityId && item.version === sourceVersion);
    if (!source || !source.contract || typeof source.contract !== 'object' || Array.isArray(source.contract)) {
      setVersionState('No se puede preparar la nueva versión: el contrato fuente no es un objeto válido.');
      return;
    }
    setVersionDraftId(proposalId);
    setVersionState(null);
    setVersionDraft({ version: '', provenance: { kind: 'ceo-reviewed-feedback' },
      contract: source.contract as Record<string, unknown>, required_permissions: source.required_permissions ?? [],
      risks: source.risks ?? [], dependencies: source.dependencies ?? [], tests: [],
      compatibility: source.compatibility ?? {}, evidence: [] });
    setVersionContractText(JSON.stringify(source.contract, null, 2));
    setVersionTestsText('');
    setVersionEvidenceText('');
  };

  const submitVersionDraft = async (event: React.FormEvent, proposalId: string) => {
    event.preventDefault();
    if (!feedbackPort || !versionDraft) return;
    try {
      const contract = JSON.parse(versionContractText) as unknown;
      if (!contract || typeof contract !== 'object' || Array.isArray(contract)) throw new Error('El contrato debe ser un objeto JSON.');
      const result = await feedbackPort.registerFeedbackCapabilityVersion(projectId, proposalId, {
        ...versionDraft, contract: contract as Record<string, unknown>,
        tests: versionTestsText.split('\n').map((value) => value.trim()).filter(Boolean),
        evidence: versionEvidenceText.split('\n').map((value) => value.trim()).filter(Boolean),
      });
      if (result.kind === 'ready') {
        setVersionState(`Registrada versión ${result.data.version} (${result.data.status}); no autoriza ejecución.`);
        setVersionDraftId(null);
        await Promise.all([feedbackQuery.refetch(), capabilitiesQuery.refetch()]);
      } else {
        setVersionState(result.kind === 'error' ? `${result.code}: ${result.message}`
          : result.kind === 'forbidden' ? result.reason : 'No se pudo registrar la nueva versión.');
      }
    } catch (error) {
      setVersionState(error instanceof Error ? error.message : 'El contrato no es JSON válido.');
    }
  };

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

      {feedbackPort && <section className="office-capability-feedback" aria-labelledby="office-capability-feedback-title">
        <h4 id="office-capability-feedback-title">Correcciones propuestas</h4>
        <p>Las propuestas quedan vinculadas a una versión y evidencia. No cambian skills ni instrucciones activas automáticamente.</p>
        {capabilities.length > 0 && <form className="office-form" onSubmit={(event) => void submitFeedback(event)}>
          <label className="office-form-field">Versión de capacidad
            <select className="office-form-control" aria-label="Versión para corrección" value={selectedValue}
              onChange={(event) => setSelectedCapability(event.target.value)}>
              {capabilities.map((item) => <option key={`${item.capability_id}@${item.version}`} value={`${item.capability_id}@${item.version}`}>{item.capability_id} · {item.version}</option>)}
            </select>
          </label>
          <label className="office-form-field">Corrección observada
            <textarea className="office-form-control" required maxLength={4000} value={correction}
              onChange={(event) => setCorrection(event.target.value)} />
          </label>
          <label className="office-form-field">ID de trabajo canónico (opcional)
            <input className="office-form-control" value={workId}
              onChange={(event) => setWorkId(event.target.value)} />
          </label>
          <label className="office-form-field">Referencias de evidencia (una por línea; exige trabajo o evidencia)
            <textarea className="office-form-control" value={evidenceText}
              onChange={(event) => setEvidenceText(event.target.value)} />
          </label>
          <button type="submit" disabled={submitting || !capabilities.length}>{submitting ? 'Guardando…' : 'Proponer corrección'}</button>
          {submitState && <p role="status">{submitState}</p>}
        </form>}
        {feedbackQuery.isLoading && <p role="status">Consultando propuestas guardadas…</p>}
        {reviewState && <p role="status">{reviewState}</p>}
        {feedbackQuery.data && <DataStatePanel state={feedbackQuery.data} renderReady={(items) => items.length ? (
          <ul className="office-capability-catalog__list">{items.map((item) => <li key={item.id} className="office-capability-catalog__item">
            <strong>{item.capability_id} · {item.version} · {item.status}</strong>
            <p>{item.correction}</p><small>{item.evidence.length} referencias · guardada por {item.created_by} · aplicada: {item.applied ? `sí, versión ${item.applied_capability_version}` : 'no'}</small>
            {item.reviewed_by && <small>Revisada por {item.reviewed_by}{item.reviewed_at ? ` · ${new Date(item.reviewed_at).toLocaleString()}` : ''}</small>}
            {item.status === 'proposed' && <div className="office-capability-feedback__actions">
              <button type="button" disabled={!!reviewingId} onClick={() => void reviewFeedback(item.id, 'accepted')}>{reviewingId === item.id ? 'Guardando…' : 'Aceptar propuesta'}</button>
              <button type="button" disabled={!!reviewingId} onClick={() => void reviewFeedback(item.id, 'rejected')}>Rechazar propuesta</button>
            </div>}
            {item.status === 'accepted' && !item.applied && <>
              <button type="button" onClick={() => beginVersionDraft(item.id, item.capability_id, item.version)}>Preparar nueva versión</button>
              {versionDraftId === item.id && versionDraft && <form className="office-form" onSubmit={(event) => void submitVersionDraft(event, item.id)}>
                <p role="note">La corrección no se inserta automáticamente. Revisa el contrato completo y registra una versión inmutable; seguirá sin autorizar ejecución.</p>
                <label className="office-form-field">Versión nueva
                  <input className="office-form-control" required value={versionDraft.version} onChange={(event) => setVersionDraft({ ...versionDraft, version: event.target.value })} />
                </label>
                <label className="office-form-field">Contrato completo (JSON)
                  <textarea className="office-form-control office-form-control--textarea" required rows={8} value={versionContractText} onChange={(event) => setVersionContractText(event.target.value)} />
                </label>
                <label className="office-form-field">Referencias de pruebas (una por línea)
                  <textarea className="office-form-control" required value={versionTestsText} onChange={(event) => setVersionTestsText(event.target.value)} />
                </label>
                <label className="office-form-field">Referencias de evidencia (una por línea)
                  <textarea className="office-form-control" required value={versionEvidenceText} onChange={(event) => setVersionEvidenceText(event.target.value)} />
                </label>
                <button type="submit">Registrar versión revisada</button>
              </form>}
            </>}
          </li>)}</ul>
        ) : <p>No hay correcciones propuestas en este proyecto.</p>} />}
        {versionState && <p role="status">{versionState}</p>}
      </section>}
    </section>
  );
};
