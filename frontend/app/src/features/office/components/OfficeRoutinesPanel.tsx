import React, { useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { AaoRoutinePort, RoutineInput } from '../../../data/ports/AaoRoutinePort';
import type { DataState, ProjectSummary } from '../../../domain/models';
import { Button } from '../../../components/ui/Button';
import './office-forms.css';

interface Props {
  projects: DataState<ProjectSummary[]>;
  port: AaoRoutinePort;
  sessionId: string;
  isCeoSession: boolean;
}

function failure(result: DataState<unknown>): string {
  if (result.kind === 'error') return `${result.code}: ${result.message}`;
  if (result.kind === 'forbidden' || result.kind === 'unavailable') return result.reason;
  return 'No se pudo confirmar el cambio. Actualiza antes de volver a intentarlo.';
}

/** All scheduling and occurrence creation live in AAO. This panel only submits explicit commands. */
export function OfficeRoutinesPanel({ projects, port, sessionId, isCeoSession }: Props) {
  const choices = projects.kind === 'ready' ? projects.data : [];
  const [requestedId, setRequestedId] = useState('');
  const project = choices.find((p) => p.id === requestedId) || choices.find((p) => p.status === 'ACTIVE') || choices[0];
  return <section className="office-form-panel" aria-labelledby="office-routines-title">
    <h3 id="office-routines-title" className="office-form-panel__title">Rutinas persistentes</h3>
    <p className="office-form-panel__description">Generan solicitudes en Entrada, no autorizan su ejecución. Requiere el servicio PM del backend habilitado; esta vista no confirma que esté funcionando. El navegador no programa trabajos.</p>
    {choices.length === 0 ? <p role="status">No hay proyectos disponibles para consultar rutinas.</p> : <>
      <label className="office-form-field office-capability-catalog__project">Proyecto de las rutinas
        <select className="office-form-control" value={project.id} onChange={(e) => setRequestedId(e.target.value)}>
          {choices.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </label>
      <ProjectRoutines key={`${sessionId}:${project.id}`} project={project} port={port} sessionId={sessionId} isCeoSession={isCeoSession} />
    </>}
  </section>;
}

function ProjectRoutines({ project, port, sessionId, isCeoSession }: Omit<Props, 'projects'> & { project: ProjectSummary }) {
  const client = useQueryClient();
  const queryKey = ['office-routines', sessionId, project.id];
  const query = useQuery({ queryKey, queryFn: () => port.listRoutines(project.id), refetchInterval: 15_000 });
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [criteria, setCriteria] = useState('');
  const [minutes, setMinutes] = useState('1440');
  const [firstRun, setFirstRun] = useState('');
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const lastAttempt = useRef<{ fingerprint: string; input: RoutineInput } | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const refresh = () => client.invalidateQueries({ queryKey });

  async function command(run: () => Promise<DataState<unknown>>, success: string) {
    if (lock.current || !isCeoSession) return;
    lock.current = true; setBusy(true); setError(''); setMessage('');
    try {
      const result = await run();
      if (result.kind === 'ready') { setMessage(success); await refresh(); }
      else setError(failure(result));
    } catch { setError('No se pudo confirmar la respuesta. Reintenta sin cambiar el formulario para reutilizar la misma solicitud.'); }
    finally { lock.current = false; setBusy(false); }
  }

  async function create(event: React.FormEvent) {
    event.preventDefault();
    const acceptance = criteria.split('\n').map((line) => line.trim()).filter(Boolean);
    const interval = Number(minutes) * 60;
    const date = new Date(`${firstRun}:00Z`);
    if (!title.trim() || !acceptance.length || acceptance.length > 50 || acceptance.some((line) => line.length > 5000)
      || !Number.isInteger(interval) || interval < 60 || interval > 31536000 || Number.isNaN(date.getTime())) {
      setError('Revisa el título, los criterios (1–50), el intervalo y la primera fecha UTC.'); return;
    }
    const body = { title: title.trim(), description, acceptance_criteria: acceptance, interval_seconds: interval, first_run_at: date.toISOString() };
    const fingerprint = JSON.stringify(body);
    if (lastAttempt.current?.fingerprint !== fingerprint) {
      lastAttempt.current = { fingerprint, input: { ...body, idempotency_key: crypto.randomUUID() } };
    }
    const input = lastAttempt.current.input;
    await command(() => port.createRoutine(project.id, input), 'Rutina registrada. El listado muestra el estado persistido en AAO.');
  }

  const result = query.data;
  return <div className="office-routines">
    <div className="office-form-panel__actions">
      <Button type="button" onClick={() => void query.refetch()} disabled={query.isFetching}>Actualizar rutinas</Button>
    </div>
    {query.isPending && <p role="status">Cargando rutinas…</p>}
    {query.isError && <p role="alert">No se pudo consultar el backend.</p>}
    {result && result.kind !== 'ready' && <p role="alert">{failure(result)}</p>}
    {result?.kind === 'ready' && (result.data.length === 0 ? <p role="status">No hay rutinas registradas en este proyecto.</p> :
      <ul className="office-capability-catalog__list">{result.data.map((routine) => <li key={routine.id} className="office-capability-catalog__item">
        <strong>{routine.template.title}</strong>
        <span>{routine.enabled ? 'Habilitada para generar solicitudes' : 'Pausada'}</span>
        <span>Intervalo fijo: {routine.interval_seconds / 60} minutos</span>
        <span>{routine.enabled ? 'Próxima solicitud prevista' : 'Fecha pendiente (no se genera mientras esté pausada)'}: <time dateTime={routine.next_run_at}>{new Date(routine.next_run_at).toISOString()}</time></span>
        {routine.template.description && <p>{routine.template.description}</p>}
        <ul>{routine.template.acceptance_criteria.map((criterion, index) => <li key={index}>{criterion}</li>)}</ul>
        <small>Autorizada por: {routine.authorized_by} · ID: {routine.id}</small>
        {isCeoSession && <Button type="button" disabled={busy} aria-label={`${routine.enabled ? 'Pausar' : 'Reanudar'} ${routine.template.title}`}
          onClick={() => void command(() => port.setRoutineEnabled(project.id, routine.id, !routine.enabled), 'Cambio registrado. Pausar no cancela trabajos existentes.')}>
          {routine.enabled ? 'Pausar' : 'Reanudar'}
        </Button>}
      </li>)}</ul>)}
    <p className="office-form-panel__description">Pausar no cancela trabajos existentes. Al reanudar, una fecha vencida puede generar una solicitud en la siguiente consulta del PM; los intervalos perdidos se agrupan, no se reproducen todos.</p>
    {isCeoSession && (project.status === 'ACTIVE' ? <form onSubmit={(e) => void create(e)} className="office-routines__form">
      <h4>Autorizar una rutina</h4>
      <label className="office-form-field">Título de la rutina<input className="office-form-control" required maxLength={200} value={title} disabled={busy} onChange={(e) => setTitle(e.target.value)} /></label>
      <label className="office-form-field">Contexto de la rutina<textarea className="office-form-control" maxLength={5000} value={description} disabled={busy} onChange={(e) => setDescription(e.target.value)} /></label>
      <label className="office-form-field">Criterios de aceptación (uno por línea)<textarea className="office-form-control" required value={criteria} disabled={busy} onChange={(e) => setCriteria(e.target.value)} /></label>
      <div className="office-routines__schedule">
        <label className="office-form-field">Intervalo fijo (minutos)<input className="office-form-control" type="number" required min={1} max={525600} step={1} value={minutes} disabled={busy} onChange={(e) => setMinutes(e.target.value)} /></label>
        <label className="office-form-field">Primera solicitud (UTC)<input className="office-form-control" type="datetime-local" required step={60} value={firstRun} disabled={busy} onChange={(e) => setFirstRun(e.target.value)} /></label>
      </div>
      <p className="office-form-panel__description">Intervalos fijos en UTC, no días de calendario local. Reintentar sin cambiar campos reutiliza la solicitud durante esta sesión de edición; cambiar campos autoriza una rutina diferente. Esta autorización no concede grants ni inicia un modelo.</p>
      <Button type="submit" disabled={busy || !title.trim() || !criteria.trim() || !firstRun}>Autorizar rutina</Button>
    </form> : <p>Solo se crean rutinas en proyectos activos.</p>)}
    {message && <p role="status">{message}</p>}
    {error && <p role="alert">{error}</p>}
  </div>;
}
