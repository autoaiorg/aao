import React, { useMemo, useState } from 'react';
import type { DataState, ProjectSummary } from '../../../domain/models';
import type { CEOWorkRequest, CreatedWorkRequest } from '../../../data/ports/AaoWorkCommandPort';
import { Button } from '../../../components/ui/Button';

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
      }));
    } catch {
      setResult({ kind: 'error', code: 'REQUEST_FAILED', message: 'No se pudo enviar la solicitud.', retryable: true });
    } finally {
      setSaving(false);
    }
  };

  const inputStyle: React.CSSProperties = {
    width: '100%', padding: '8px 10px', border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-sm, 6px)', background: 'var(--bg-surface)', color: 'var(--text-primary)',
  };

  return (
    <section aria-labelledby="office-work-request-title" style={{ border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-lg, 12px)', padding: 16, background: 'var(--bg-surface)' }}>
      <h3 id="office-work-request-title" style={{ margin: '0 0 4px', fontSize: 16 }}>Dirigir trabajo a un proyecto</h3>
      <p style={{ margin: '0 0 14px', color: 'var(--text-secondary)', fontSize: 12 }}>
        Crea una solicitud persistente en Entrada. No la admite ni inicia una ejecución.
      </p>
      {projects.kind !== 'ready' ? (
        <p role="status" style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
          {projects.kind === 'forbidden' ? projects.reason : projects.kind === 'error' ? projects.message : 'Proyectos LIVE no disponibles; no se puede enviar la solicitud.'}
        </p>
      ) : activeProjects.length === 0 ? (
        <p role="status" style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No hay proyectos activos disponibles.</p>
      ) : (
        <form onSubmit={submit} style={{ display: 'grid', gap: 10, maxWidth: 720 }}>
          <label style={{ display: 'grid', gap: 4, fontSize: 12 }}>Proyecto activo
            <select aria-label="Proyecto activo" required value={projectId} onChange={(event) => setProjectId(event.target.value)} style={inputStyle}>
              <option value="">Selecciona un proyecto</option>
              {activeProjects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
            </select>
          </label>
          <label style={{ display: 'grid', gap: 4, fontSize: 12 }}>Solicitud
            <input aria-label="Solicitud" required maxLength={200} value={title} onChange={(event) => setTitle(event.target.value)} style={inputStyle} />
          </label>
          <label style={{ display: 'grid', gap: 4, fontSize: 12 }}>Contexto (opcional)
            <textarea aria-label="Contexto" maxLength={5000} rows={3} value={description} onChange={(event) => setDescription(event.target.value)} style={inputStyle} />
          </label>
          <label style={{ display: 'grid', gap: 4, fontSize: 12 }}>Criterios de aceptación (uno por línea)
            <textarea aria-label="Criterios de aceptación" required rows={3} value={criteria} onChange={(event) => setCriteria(event.target.value)} style={inputStyle} />
          </label>
          <div><Button type="submit" disabled={saving || !projectId || !title.trim() || !criteria.trim()}>{saving ? 'Guardando…' : 'Registrar en Entrada'}</Button></div>
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
