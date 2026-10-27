import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { OfficeRoutinesPanel } from '../features/office/components/OfficeRoutinesPanel';
import type { AaoRoutinePort, ProjectRoutine } from '../data/ports/AaoRoutinePort';
import type { DataState, ProjectSummary } from '../domain/models';
const ready = <T,>(data: T): DataState<T> => ({ kind: 'ready', origin: 'live', fetchedAt: 'now', data });
const projects = ready<ProjectSummary[]>([{ id: 'a', name: 'Proyecto A', status: 'ACTIVE' }, { id: 'b', name: 'Proyecto B', status: 'PAUSED' }]);
const routine: ProjectRoutine = { id: 'routine-a', template: { title: 'Informe periódico', description: 'Contexto', acceptance_criteria: ['Referencias'] },
  interval_seconds: 3600, next_run_at: '2026-10-27T10:00:00Z', enabled: true, authorized_by: 'ceo', created_at: '2026-10-26T10:00:00Z', execution_authorized: false };
function port(): AaoRoutinePort {
  return { listRoutines: vi.fn().mockResolvedValue(ready([routine])),
    createRoutine: vi.fn().mockResolvedValue(ready({ id: 'new', created: true })),
    setRoutineEnabled: vi.fn().mockResolvedValue(ready({ id: routine.id, enabled: false })) };
}
function mount(api = port(), isCeoSession = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = (sessionId: string) => <QueryClientProvider client={client}><OfficeRoutinesPanel projects={projects} port={api} sessionId={sessionId} isCeoSession={isCeoSession} /></QueryClientProvider>;
  const result = render(view('session-a'));
  return { api, ...result, changeSession: () => result.rerender(view('session-b')) };
}
function fill() {
  fireEvent.change(screen.getByLabelText('Título de la rutina'), { target: { value: 'Revisar avances' } });
  fireEvent.change(screen.getByLabelText('Criterios de aceptación (uno por línea)'), { target: { value: 'Resumen\nEvidencia' } });
  fireEvent.change(screen.getByLabelText('Primera solicitud (UTC)'), { target: { value: '2026-10-28T09:30' } });
}
describe('LIVE durable routines', () => {
  it('reads persisted state and pauses without claiming execution or canceling existing work', async () => {
    const { api } = mount();
    expect(await screen.findByText('Informe periódico')).toBeInTheDocument();
    expect(screen.getByText(/Requiere el servicio PM del backend/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Pausar Informe periódico' }));
    await waitFor(() => expect(api.setRoutineEnabled).toHaveBeenCalledWith('a', 'routine-a', false));
    await waitFor(() => expect(api.listRoutines).toHaveBeenCalledTimes(2));
    expect(screen.getByText(/^Pausar no cancela trabajos existentes/)).toBeInTheDocument();
  });
  it('resumes a paused routine and keeps the canonical state when a command is rejected', async () => {
    const api = port();
    vi.mocked(api.listRoutines).mockResolvedValue(ready([{ ...routine, enabled: false }]));
    vi.mocked(api.setRoutineEnabled).mockResolvedValue({ kind: 'forbidden', reason: 'Sesión caducada' });
    mount(api);
    fireEvent.click(await screen.findByRole('button', { name: 'Reanudar Informe periódico' }));
    expect(await screen.findByText('Sesión caducada')).toBeInTheDocument();
    expect(api.setRoutineEnabled).toHaveBeenCalledWith('a', 'routine-a', true);
    expect(screen.getByText('Pausada')).toBeInTheDocument();
    expect(api.listRoutines).toHaveBeenCalledTimes(1);
  });
  it('does not submit a whitespace-only title or criteria', async () => {
    const { api } = mount(); fill();
    fireEvent.change(screen.getByLabelText('Título de la rutina'), { target: { value: '   ' } });
    expect(screen.getByRole('button', { name: 'Autorizar rutina' })).toBeDisabled();
    expect(api.createRoutine).not.toHaveBeenCalled();
  });
  it('creates an explicitly authorized INBOX template with UTC date and reuses the key after an uncertain response', async () => {
    const api = port();
    vi.mocked(api.createRoutine).mockResolvedValueOnce({ kind: 'error', code: 'NETWORK_ERROR', message: 'Respuesta perdida', retryable: true })
      .mockResolvedValueOnce(ready({ id: 'new', created: false }));
    mount(api); fill();
    fireEvent.click(screen.getByRole('button', { name: 'Autorizar rutina' }));
    expect(await screen.findByText(/Respuesta perdida/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Autorizar rutina' }));
    await waitFor(() => expect(api.createRoutine).toHaveBeenCalledTimes(2));
    const first = vi.mocked(api.createRoutine).mock.calls[0];
    expect(first[1]).toMatchObject({ title: 'Revisar avances', acceptance_criteria: ['Resumen', 'Evidencia'], interval_seconds: 86400, first_run_at: '2026-10-28T09:30:00.000Z' });
    expect(first[1].idempotency_key).toMatch(/^[a-f0-9-]{36}$/);
    expect(vi.mocked(api.createRoutine).mock.calls[1]).toEqual(first);
    expect(await screen.findByText(/Rutina registrada/)).toBeInTheDocument();
  });
  it('is read-only for non-CEO sessions', async () => {
    mount(port(), false);
    expect(await screen.findByText('Informe periódico')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Pausar/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Autorizar rutina' })).not.toBeInTheDocument();
  });
  it('switches project without stale draft or authority for paused projects', async () => {
    const { api } = mount(); fill();
    fireEvent.change(screen.getByLabelText('Proyecto de las rutinas'), { target: { value: 'b' } });
    await waitFor(() => expect(api.listRoutines).toHaveBeenCalledWith('b'));
    expect(screen.queryByLabelText('Título de la rutina')).not.toBeInTheDocument();
    expect(screen.getByText(/Solo se crean rutinas en proyectos activos/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Proyecto de las rutinas'), { target: { value: 'a' } });
    expect(screen.getByLabelText('Título de la rutina')).toHaveValue('');
  });
  it('reports read errors and offers a backend refresh without fictitious routines', async () => {
    const api = port(); vi.mocked(api.listRoutines).mockResolvedValue({ kind: 'forbidden', reason: 'Sin project.read' });
    mount(api);
    expect(await screen.findByText('Sin project.read')).toBeInTheDocument();
    expect(screen.queryByText('Informe periódico')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Actualizar rutinas' }));
    await waitFor(() => expect(api.listRoutines).toHaveBeenCalledTimes(2));
  });
  it('resets drafts and performs a separate query after changing authentication session', async () => {
    const { api, changeSession } = mount(); fill();
    changeSession();
    expect(screen.getByLabelText('Título de la rutina')).toHaveValue('');
    await waitFor(() => expect(api.listRoutines).toHaveBeenCalledTimes(2));
  });
  it('polls the backend while open; it does not materialize occurrences in the browser', async () => {
    vi.useFakeTimers();
    try {
      const { api } = mount();
      await act(async () => { await Promise.resolve(); await Promise.resolve(); });
      expect(api.listRoutines).toHaveBeenCalledTimes(1);
      await act(async () => { await vi.advanceTimersByTimeAsync(15_000); });
      expect(api.listRoutines).toHaveBeenCalledTimes(2);
      expect(api.createRoutine).not.toHaveBeenCalled();
      expect(api.setRoutineEnabled).not.toHaveBeenCalled();
    } finally { vi.useRealTimers(); }
  });
});
