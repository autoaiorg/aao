import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { OfficeConversationPanel } from '../features/office/components/OfficeConversationPanel';
import type { AaoConversationPort } from '../data/ports/AaoConversationPort';
import type { DataState, ProjectSummary } from '../domain/models';

const projects: DataState<ProjectSummary[]> = { kind: 'ready', origin: 'live', fetchedAt: 'now', data: [
  { id: 'project-active', name: 'Proyecto activo', status: 'ACTIVE' },
  { id: 'project-paused', name: 'Proyecto pausado', status: 'PAUSED' },
] };
const conversation = { id: 'conversation-1', project_id: 'project-active', title: 'Plan', created_at: '2026-10-25T10:00:00Z', updated_at: '2026-10-25T10:00:00Z' };
const message = { id: 'message-1', sender: 'CEO' as const, body: 'Preparar el plan', related_work_id: null, work_status: null, latest_execution: null, created_at: '2026-10-25T10:00:00Z' };
const ready = <T,>(data: T): DataState<T> => ({ kind: 'ready', origin: 'live', fetchedAt: 'now', data });

function setup(port: AaoConversationPort) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><OfficeConversationPanel projects={projects} port={port} sessionId="session-a" onOpenBoard={vi.fn()} /></QueryClientProvider>);
}

describe('office persistent project conversation', () => {
  it('streams a provider response and does not create work merely by conversing', async () => {
    const port: AaoConversationPort = {
      listProjectConversations: vi.fn().mockResolvedValue(ready([conversation])),
      listConversationMessages: vi.fn().mockResolvedValue(ready([message])),
      createProjectConversation: vi.fn(),
      appendCEOConversationMessage: vi.fn().mockResolvedValue(ready(message)),
      streamCEOConversationTurn: vi.fn().mockImplementation(async (_project, _conversation, _body, onDelta) => {
        onDelta('Respuesta en directo');
        return ready({ message_id: 'response-1' });
      }),
      createWorkRequestFromMessage: vi.fn(),
    };
    setup(port);
    await screen.findByText('Preparar el plan');
    fireEvent.change(screen.getByLabelText('Mensaje CEO'), { target: { value: 'Revisar el presupuesto' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar a AAO' }));
    await waitFor(() => expect(port.streamCEOConversationTurn).toHaveBeenCalledWith('project-active', 'conversation-1', 'Revisar el presupuesto', expect.any(Function)));
    expect(await screen.findByText(/Respuesta AAO recibida y persistida/)).toBeInTheDocument();
    expect(port.createWorkRequestFromMessage).not.toHaveBeenCalled();
    expect(screen.queryByRole('option', { name: 'Proyecto pausado' })).not.toBeInTheDocument();
  });

  it('allows the CEO to turn an AAO proposal into an explicit INBOX task', async () => {
    const assistantMessage = { ...message, sender: 'AAO' as const, body: 'Propuesta: revisar el presupuesto' };
    const port: AaoConversationPort = {
      listProjectConversations: vi.fn().mockResolvedValue(ready([conversation])),
      listConversationMessages: vi.fn().mockResolvedValue(ready([assistantMessage])),
      createProjectConversation: vi.fn(),
      appendCEOConversationMessage: vi.fn(),
      streamCEOConversationTurn: vi.fn(),
      createWorkRequestFromMessage: vi.fn().mockResolvedValue(ready({ id: 'work-1', status: 'INBOX', created: true })),
    };
    setup(port);
    await screen.findByText('Propuesta: revisar el presupuesto');
    fireEvent.click(screen.getByRole('button', { name: 'Convertir en solicitud de trabajo…' }));
    fireEvent.change(screen.getByLabelText('Título del trabajo para message-1'), { target: { value: 'Revisar presupuesto' } });
    fireEvent.change(screen.getByLabelText('Criterios de aceptación para message-1'), { target: { value: 'Informe revisado' } });
    fireEvent.click(screen.getByRole('button', { name: 'Crear solicitud INBOX' }));
    await waitFor(() => expect(port.createWorkRequestFromMessage).toHaveBeenCalledWith('project-active', 'conversation-1', 'message-1', {
      title: 'Revisar presupuesto', acceptance_criteria: ['Informe revisado'],
    }));
  });

  it('requires explicit title and acceptance criteria, then links the persisted work request', async () => {
    const onOpenBoard = vi.fn();
    const workId = '00000000-0000-4000-8000-000000000042';
    let linkedWorkId: string | null = null;
    const port: AaoConversationPort = {
      listProjectConversations: vi.fn().mockResolvedValue(ready([conversation])),
      listConversationMessages: vi.fn().mockImplementation(async () => ready([{
        ...message, related_work_id: linkedWorkId, work_status: linkedWorkId ? 'INBOX' : null,
        latest_execution: linkedWorkId ? { id: '00000000-0000-4000-8000-000000000043', status: 'SUCCEEDED', backend: 'codex', provider: 'openai', model: 'gpt-6-luna' } : null,
      }])),
      createProjectConversation: vi.fn(),
      appendCEOConversationMessage: vi.fn(),
      streamCEOConversationTurn: vi.fn(),
      createWorkRequestFromMessage: vi.fn().mockImplementation(async () => {
        linkedWorkId = workId;
        return ready({ id: workId, status: 'INBOX', created: true });
      }),
    };
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><OfficeConversationPanel projects={projects} port={port} sessionId="session-work" onOpenBoard={onOpenBoard} /></QueryClientProvider>);

    await screen.findByText('Preparar el plan');
    fireEvent.click(screen.getByRole('button', { name: 'Convertir en solicitud de trabajo…' }));
    fireEvent.change(screen.getByLabelText('Título del trabajo para message-1'), { target: { value: 'Preparar análisis' } });
    fireEvent.change(screen.getByLabelText('Criterios de aceptación para message-1'), { target: { value: 'Hallazgos documentados\nRevisión completada' } });
    fireEvent.click(screen.getByRole('button', { name: 'Crear solicitud INBOX' }));

    await waitFor(() => expect(port.createWorkRequestFromMessage).toHaveBeenCalledWith('project-active', 'conversation-1', 'message-1', {
      title: 'Preparar análisis', acceptance_criteria: ['Hallazgos documentados', 'Revisión completada'],
    }));
    await waitFor(() => expect(screen.getByRole('button', { name: `Abrir trabajo ${workId}` })).toBeInTheDocument());
    expect(screen.getByText('Estado del trabajo: INBOX')).toBeInTheDocument();
    expect(screen.getByText(/Última ejecución SUCCEEDED · openai \/ gpt-6-luna/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: `Abrir trabajo ${workId}` }));
    expect(onOpenBoard).toHaveBeenCalledWith('project-active');
    expect(screen.getByText(/no se ha admitido ni ejecutado/)).toBeInTheDocument();
  });
});
