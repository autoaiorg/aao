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
      listAssignableAgents: vi.fn().mockResolvedValue(ready([
        { principal_id: 'worker-1', display_name: 'Agente de implementación' },
      ])),
      listConversationMessages: vi.fn().mockResolvedValue(ready([message])),
      createProjectConversation: vi.fn(),
      appendCEOConversationMessage: vi.fn().mockResolvedValue(ready(message)),
      streamCEOConversationTurn: vi.fn().mockImplementation(async (_project, _conversation, _body, _key, onDelta) => {
        onDelta('Respuesta en directo');
        return ready({ message_id: 'response-1' });
      }),
      createWorkRequestFromMessage: vi.fn(),
      createWorkRequestFromConversation: vi.fn(),
      createWorkGroupFromConversation: vi.fn(),
      proposeWorkGroupFromConversation: vi.fn(),
    };
    setup(port);
    await screen.findByText('Preparar el plan');
    fireEvent.change(screen.getByLabelText('Mensaje CEO'), { target: { value: 'Revisar el presupuesto' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar a AAO' }));
    await waitFor(() => expect(port.streamCEOConversationTurn).toHaveBeenCalledWith('project-active', 'conversation-1', 'Revisar el presupuesto', expect.any(String), expect.any(Function)));
    expect(await screen.findByText(/Respuesta AAO recibida y persistida/)).toBeInTheDocument();
    expect(port.createWorkRequestFromMessage).not.toHaveBeenCalled();
    expect(screen.queryByRole('option', { name: 'Proyecto pausado' })).not.toBeInTheDocument();
  });

  it('reuses the same idempotency key when retrying an interrupted logical turn', async () => {
    const interrupted: DataState<{ message_id: string }> = {
      kind: 'error', code: 'STREAM_ERROR', message: 'connection interrupted', retryable: true,
    };
    const port: AaoConversationPort = {
      listProjectConversations: vi.fn().mockResolvedValue(ready([conversation])),
      listAssignableAgents: vi.fn().mockResolvedValue(ready([])),
      listConversationMessages: vi.fn().mockResolvedValue(ready([message])),
      createProjectConversation: vi.fn(), appendCEOConversationMessage: vi.fn(),
      streamCEOConversationTurn: vi.fn()
        .mockResolvedValueOnce(interrupted)
        .mockResolvedValueOnce(ready({ message_id: 'reply-1' })),
      createWorkRequestFromMessage: vi.fn(), createWorkRequestFromConversation: vi.fn(), createWorkGroupFromConversation: vi.fn(), proposeWorkGroupFromConversation: vi.fn(),
    };
    setup(port);
    await screen.findByText('Preparar el plan');
    fireEvent.change(screen.getByLabelText('Mensaje CEO'), { target: { value: 'Analiza este alcance' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar a AAO' }));
    await waitFor(() => expect(port.streamCEOConversationTurn).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('button', { name: 'Enviar a AAO' }));
    await waitFor(() => expect(port.streamCEOConversationTurn).toHaveBeenCalledTimes(2));
    const first = vi.mocked(port.streamCEOConversationTurn).mock.calls[0];
    const second = vi.mocked(port.streamCEOConversationTurn).mock.calls[1];
    expect(first[2]).toBe('Analiza este alcance');
    expect(second[2]).toBe(first[2]);
    expect(second[3]).toBe(first[3]);
  });

  it('lets the CEO retry a persisted pending turn after reopening the thread', async () => {
    const pending = { ...message, turn_status: 'PENDING' as const, turn_idempotency_key: 'b7f4938a-98d3-45a7-a5d7-2bb3e2b4de34' };
    const port: AaoConversationPort = {
      listProjectConversations: vi.fn().mockResolvedValue(ready([conversation])),
      listAssignableAgents: vi.fn().mockResolvedValue(ready([])),
      listConversationMessages: vi.fn().mockResolvedValue(ready([pending])),
      createProjectConversation: vi.fn(), appendCEOConversationMessage: vi.fn(),
      streamCEOConversationTurn: vi.fn().mockResolvedValue(ready({ message_id: 'reply-recovered' })),
      createWorkRequestFromMessage: vi.fn(), createWorkRequestFromConversation: vi.fn(),
      createWorkGroupFromConversation: vi.fn(), proposeWorkGroupFromConversation: vi.fn(),
    };
    setup(port);
    await screen.findByText('Preparar el plan');
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar si quedó interrumpida' }));
    await waitFor(() => expect(port.streamCEOConversationTurn).toHaveBeenCalledWith(
      'project-active', 'conversation-1', 'Preparar el plan', pending.turn_idempotency_key, expect.any(Function),
    ));
  });

  it('structures CEO-confirmed parent and dependent tasks from the conversation thread', async () => {
    const port: AaoConversationPort = {
      listProjectConversations: vi.fn().mockResolvedValue(ready([conversation])),
      listAssignableAgents: vi.fn().mockResolvedValue(ready([
        { principal_id: 'worker-1', display_name: 'Agente de implementación' },
      ])),
      listConversationMessages: vi.fn().mockResolvedValue(ready([message, { ...message, id: 'message-2', sender: 'AAO', body: 'Propongo documentar los hallazgos.' } ])),
      createProjectConversation: vi.fn(), appendCEOConversationMessage: vi.fn(), streamCEOConversationTurn: vi.fn(),
      createWorkRequestFromMessage: vi.fn(),
      createWorkRequestFromConversation: vi.fn().mockResolvedValue(ready({ id: 'work-1', status: 'INBOX', created: true })),
      createWorkGroupFromConversation: vi.fn().mockResolvedValue(ready({
        id: 'group-1', project_id: 'project-active', conversation_id: 'conversation-1',
        parent_work_id: 'work-parent', status: 'INBOX', created: true,
        tasks: [{ id: 'work-child', title: 'Documentar', status: 'INBOX', assigned_principal_id: null, depends_on: [] }],
      })),
      proposeWorkGroupFromConversation: vi.fn().mockResolvedValue(ready({
        proposal: {
          title: 'Plan acordado', description: 'Resultado del hilo',
          acceptance_criteria: ['Criterios trazables'],
          tasks: [{ key: 'task-1', title: 'Investigar', description: 'Revisar fuentes', acceptance_criteria: ['Fuentes registradas'], depends_on: [] }],
        },
        based_on_message_ids: ['message-1', 'message-2'], provider: 'openai-compatible', model: 'test-model', persisted_as_work: false,
      })),
    };
    setup(port);
    await screen.findByText('Propongo documentar los hallazgos.');
    expect(screen.queryByRole('button', { name: /Convertir en solicitud/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Proponer desglose con AAO' }));
    await screen.findByText(/AAO propuso 1 tareas a partir de 2 mensajes/);
    fireEvent.change(screen.getByLabelText('Título de tarea desde conversación'), { target: { value: 'Documentar hallazgos' } });
    fireEvent.change(screen.getByLabelText('Descripción de tarea desde conversación'), { target: { value: 'A partir del hilo, documentar los hallazgos acordados.' } });
    fireEvent.change(screen.getByLabelText('Criterios de aceptación de tarea desde conversación'), { target: { value: 'Hallazgos documentados\nCEO puede revisarlos' } });
    fireEvent.change(screen.getByLabelText('Título task-1'), { target: { value: 'Documentar hallazgos' } });
    fireEvent.change(screen.getByLabelText('Criterios task-1'), { target: { value: 'Hallazgos documentados' } });
    fireEvent.click(screen.getByRole('button', { name: 'Añadir tarea' }));
    fireEvent.change(screen.getByLabelText('Título task-2'), { target: { value: 'Revisar documentación' } });
    fireEvent.change(screen.getByLabelText('Criterios task-2'), { target: { value: 'CEO puede revisarlos' } });
    fireEvent.change(screen.getByLabelText('Asignar task-2'), { target: { value: 'worker-1' } });
    fireEvent.click(screen.getByLabelText('task-1: Documentar hallazgos'));
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar desglose y crear en Entrada' }));
    await waitFor(() => expect(port.createWorkGroupFromConversation).toHaveBeenCalledWith('project-active', 'conversation-1', {
      idempotency_key: expect.any(String),
      based_on_message_ids: ['message-1', 'message-2'],
      title: 'Documentar hallazgos', description: 'A partir del hilo, documentar los hallazgos acordados.', acceptance_criteria: ['Hallazgos documentados', 'CEO puede revisarlos'],
      tasks: [
        { key: 'task-1', title: 'Documentar hallazgos', description: 'Revisar fuentes', acceptance_criteria: ['Hallazgos documentados'], depends_on: [] },
        { key: 'task-2', title: 'Revisar documentación', description: '', acceptance_criteria: ['CEO puede revisarlos'], depends_on: ['task-1'], assigned_principal_id: 'worker-1' },
      ],
    }));
    expect(await screen.findByText(/no se ha admitido ni ejecutado/)).toBeInTheDocument();
    expect(port.createWorkRequestFromMessage).not.toHaveBeenCalled();
  });

  it('asks AAO for a reviewable breakdown based on the whole persisted thread', async () => {
    const port: AaoConversationPort = {
      listProjectConversations: vi.fn().mockResolvedValue(ready([conversation])),
      listAssignableAgents: vi.fn().mockResolvedValue(ready([])),
      listConversationMessages: vi.fn().mockResolvedValue(ready([
        message, { ...message, id: 'message-2', sender: 'AAO', body: 'Acuerdo del hilo.' },
      ])),
      createProjectConversation: vi.fn(), appendCEOConversationMessage: vi.fn(), streamCEOConversationTurn: vi.fn(),
      createWorkRequestFromMessage: vi.fn(), createWorkRequestFromConversation: vi.fn(), createWorkGroupFromConversation: vi.fn(),
      proposeWorkGroupFromConversation: vi.fn().mockResolvedValue(ready({
        proposal: {
          title: 'Plan acordado', description: 'Resultado del hilo',
          acceptance_criteria: ['Criterios trazables'],
          tasks: [{ key: 'research', title: 'Investigar', description: 'Revisar fuentes', acceptance_criteria: ['Fuentes registradas'], depends_on: [] }],
        },
        based_on_message_ids: ['message-1', 'message-2'], provider: 'openai-compatible', model: 'test-model', persisted_as_work: false,
      })),
    };
    setup(port);
    await screen.findByText('Acuerdo del hilo.');
    fireEvent.click(screen.getByRole('button', { name: 'Proponer desglose con AAO' }));
    expect(await screen.findByDisplayValue('Plan acordado')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Investigar')).toBeInTheDocument();
    expect(await screen.findByText(/a partir de 2 mensajes/)).toBeInTheDocument();
    expect(port.proposeWorkGroupFromConversation).toHaveBeenCalledWith('project-active', 'conversation-1');
    expect(port.createWorkGroupFromConversation).not.toHaveBeenCalled();
  });
});
