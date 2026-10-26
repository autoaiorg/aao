import React, { useMemo, useState } from 'react';
import type { DataState, ProjectSummary } from '../../../domain/models';
import type { CEOWorkRequest, CreatedWorkRequest } from '../../../data/ports/AaoWorkCommandPort';
import { Button } from '../../../components/ui/Button';
import './office-forms.css';

interface OfficeWorkRequestPanelProps {
  projects: DataState<ProjectSummary[]>;
  onCreate: (projectId: string, input: CEOWorkRequest) => Promise<DataState<CreatedWorkRequest>>;
  onOpenBoard: (projectId: string) => void;
}

export const OfficeWorkRequestPanel: React.FC<OfficeWorkRequestPanelProps> = ({
  projects,
  onCreate,
  onOpenBoard,
}) => {
  const activeProjects = useMemo(
    () => projects.kind === 'ready' ? projects.data.filter((project) => (project.status || 'ACTIVE') === 'ACTIVE') : [],
    [projects],
  );
  const [projectId, setProjectId] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [criteria, setCriteria] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [result, setResult] = useState<DataState<CreatedWorkRequest> | null>(null);
  const [saving, setSaving] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const acceptance_criteria = criteria.split('\n').map((line) => line.trim()).filter(Boolean);
    if (!projectId || !title.trim() || acceptance_criteria.length === 0) return;
    setSaving(true);
    setResult(null);
    try {
      setResult(await onCreate(projectId, {
        title: title.trim(), description: description.trim(), acceptance_criteria,
        due_date: dueDate || null,
      }));
    } catch {
      setResult({ kind: 'error', code: 'REQUEST_FAILED', message: 'No se pudo enviar la solicitud.', retryable: true });
    } finally {
      setSaving(false);
    }
  };

  return (
    <section aria-labelledby="office-work-request-title" className="office-form-panel">
      <h3 id="office-work-request-title" className="office-form-panel__title">Dirigir trabajo a un proyecto</h3>
      <p className="office-form-panel__description">
        Crea una solicitud persistente en Entrada. No la admite ni inicia una ejecución.
      </p>
      {projects.kind !== 'ready' ? (
        <p role="status" style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
          {projects.kind === 'forbidden' ? projects.reason : projects.kind === 'error' ? projects.message : 'Proyectos LIVE no disponibles; no se puede enviar la solicitud.'}
        </p>
      ) : activeProjects.length === 0 ? (
        <p role="status" style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No hay proyectos activos disponibles.</p>
      ) : (
        <form onSubmit={submit} className="office-work-request-form">
          <label className="office-form-field">Proyecto activo
            <select className="office-form-control" aria-label="Proyecto activo" required value={projectId} onChange={(event) => setProjectId(event.target.value)}>
              <option value="">Selecciona un proyecto</option>
              {activeProjects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
            </select>
          </label>
          <label className="office-form-field">Solicitud
            <input className="office-form-control" aria-label="Solicitud" required maxLength={200} value={title} onChange={(event) => setTitle(event.target.value)} />
          </label>
          <label className="office-form-field">Contexto (opcional)
            <textarea className="office-form-control office-form-control--textarea" aria-label="Contexto" maxLength={5000} rows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
          </label>
          <label className="office-form-field">Fecha objetivo (opcional)
            <input className="office-form-control" aria-label="Fecha objetivo" type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} />
          </label>
          <label className="office-form-field">Criterios de aceptación (uno por línea)
            <textarea className="office-form-control office-form-control--textarea" aria-label="Criterios de aceptación" required rows={3} value={criteria} onChange={(event) => setCriteria(event.target.value)} />
          </label>
          <div className="office-form-field--wide office-form-actions"><Button type="submit" disabled={saving || !projectId || !title.trim() || !criteria.trim()}>{saving ? 'Guardando…' : 'Registrar en Entrada'}</Button></div>
        </form>
      )}
      {result?.kind === 'ready' && (
        <div role="status" style={{ marginTop: 12, fontSize: 13 }}>
          Solicitud registrada: <code>{result.data.id}</code> · INBOX
          <Button size="sm" variant="outline" onClick={() => onOpenBoard(projectId)} style={{ marginLeft: 10 }}>Abrir tablero</Button>
        </div>
      )}
      {result && result.kind !== 'ready' && (
        <p role="alert" style={{ color: 'var(--status-danger-text)', fontSize: 13 }}>
          {result.kind === 'error' ? `${result.code}: ${result.message}` : result.kind === 'forbidden' ? result.reason : 'No se pudo registrar la solicitud.'}
        </p>
      )}
    </section>
  );
};
