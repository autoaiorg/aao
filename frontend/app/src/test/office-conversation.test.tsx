import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
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

function setup(port: AaoConversationPort, onOpenBoard = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><OfficeConversationPanel projects={projects} port={port} sessionId="session-a" onOpenBoard={onOpenBoard} /></QueryClientProvider>);
  return onOpenBoard;
}

describe('office persistent project conversation', () => {
  it('sends on Enter, preserves Shift+Enter and does not submit during IME composition', async () => {
    const port: AaoConversationPort = {
      listProjectConversations: vi.fn().mockResolvedValue(ready([conversation])),
      listAssignableAgents: vi.fn().mockResolvedValue(ready([])),
      listConversationMessages: vi.fn().mockResolvedValue(ready([message])),
      createProjectConversation: vi.fn(), appendCEOConversationMessage: vi.fn(),
      streamCEOConversationTurn: vi.fn().mockResolvedValue(ready({ message_id: 'response-2' })),
      createWorkRequestFromMessage: vi.fn(), createWorkRequestFromConversation: vi.fn(),
      createWorkGroupFromConversation: vi.fn(), proposeWorkGroupFromConversation: vi.fn(),
      listProjectWorkGroups: vi.fn().mockResolvedValue(ready([])), assignWorkGroupChild: vi.fn(),
      confirmWorkGroupConsolidation: vi.fn(), createWorkGroupPartialReport: vi.fn(),
    };
    setup(port);
    await screen.findByText('Preparar el plan');
    const composer = screen.getByLabelText('Mensaje CEO');
    fireEvent.change(composer, { target: { value: 'Pregunta rápida' } });

    fireEvent.keyDown(composer, { key: 'Enter', shiftKey: true });
    fireEvent.keyDown(composer, { key: 'Enter', isComposing: true });
    expect(port.streamCEOConversationTurn).not.toHaveBeenCalled();

    fireEvent.keyDown(composer, { key: 'Enter' });
    await waitFor(() => expect(port.streamCEOConversationTurn).toHaveBeenCalledWith(
      'project-active', 'conversation-1', 'Pregunta rápida', expect.any(String), expect.any(Function),
    ));
  });

  it('acknowledges a CEO turn before the first provider delta, then replaces the placeholder with streamed text', async () => {
    let emitDelta: ((delta: string) => void) | undefined;
    let finishTurn: ((result: DataState<{ message_id: string }>) => void) | undefined;
    const port: AaoConversationPort = {
      listProjectConversations: vi.fn().mockResolvedValue(ready([conversation])),
      listAssignableAgents: vi.fn().mockResolvedValue(ready([])),
      listConversationMessages: vi.fn().mockResolvedValue(ready([message])),
      createProjectConversation: vi.fn(), appendCEOConversationMessage: vi.fn(),
      streamCEOConversationTurn: vi.fn().mockImplementation((_project, _conversation, _body, _key, onDelta) => {
        emitDelta = onDelta;
        return new Promise((resolve) => { finishTurn = resolve; });
      }),
      createWorkRequestFromMessage: vi.fn(), createWorkRequestFromConversation: vi.fn(),
      createWorkGroupFromConversation: vi.fn(), proposeWorkGroupFromConversation: vi.fn(),
      listProjectWorkGroups: vi.fn().mockResolvedValue(ready([])), assignWorkGroupChild: vi.fn(),
      confirmWorkGroupConsolidation: vi.fn(), createWorkGroupPartialReport: vi.fn(),
    };
    setup(port);
    await screen.findByText('Preparar el plan');
    fireEvent.change(screen.getByLabelText('Mensaje CEO'), { target: { value: 'Ayúdame con el alcance' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar a AAO' }));
    expect(await screen.findByText('Preparando respuesta…')).toBeInTheDocument();
    expect(screen.getByText('Ayúdame con el alcance')).toBeInTheDocument();

    await act(async () => { emitDelta?.('Primer fragmento'); });
    expect(screen.getByText('Primer fragmento')).toBeInTheDocument();
    expect(screen.queryByText('Preparando respuesta…')).not.toBeInTheDocument();
    await act(async () => { finishTurn?.(ready({ message_id: 'response-2' })); });
    expect(await screen.findByText(/Respuesta AAO recibida y persistida/)).toBeInTheDocument();
  });

  it('streams a provider response and does not create work merely by conversing', async () => {
    const port: AaoConversationPort = {
      listProjectConversations: vi.fn().mockResolvedValue(ready([conversation])),
      listAssignableAgents: vi.fn().mockResolvedValue(ready([
        { principal_id: 'worker-1', display_name: 'Agente de implementación', competencies: ['implementación'] },
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
      listProjectWorkGroups: vi.fn().mockResolvedValue(ready([])), assignWorkGroupChild: vi.fn(), confirmWorkGroupConsolidation: vi.fn(), createWorkGroupPartialReport: vi.fn(),
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

  it('opens the exact canonical work item linked from a conversation message', async () => {
    const linkedMessage = { ...message, related_work_id: 'work-linked', work_status: 'IN_REVIEW' };
    const port: AaoConversationPort = {
      listProjectConversations: vi.fn().mockResolvedValue(ready([conversation])),
      listAssignableAgents: vi.fn().mockResolvedValue(ready([])),
      listConversationMessages: vi.fn().mockResolvedValue(ready([linkedMessage])),
      createProjectConversation: vi.fn(), appendCEOConversationMessage: vi.fn(), streamCEOConversationTurn: vi.fn(),
      createWorkRequestFromMessage: vi.fn(), createWorkRequestFromConversation: vi.fn(),
      createWorkGroupFromConversation: vi.fn(), proposeWorkGroupFromConversation: vi.fn(),
      listProjectWorkGroups: vi.fn().mockResolvedValue(ready([])), assignWorkGroupChild: vi.fn(),
      confirmWorkGroupConsolidation: vi.fn(), createWorkGroupPartialReport: vi.fn(),
    };
    const onOpenBoard = setup(port);
    await screen.findByText('Preparar el plan');
    fireEvent.click(screen.getByRole('button', { name: 'Abrir trabajo work-linked' }));
    expect(onOpenBoard).toHaveBeenCalledWith('project-active', 'work-linked');
  });

  it('shows execution status for tasks confirmed from the selected conversation without rendering result payloads', async () => {
    const resultSha = 'a'.repeat(64);
    const port: AaoConversationPort = {
      listProjectConversations: vi.fn().mockResolvedValue(ready([conversation])),
      listAssignableAgents: vi.fn().mockResolvedValue(ready([])),
      listConversationMessages: vi.fn().mockResolvedValue(ready([message])),
      createProjectConversation: vi.fn(), appendCEOConversationMessage: vi.fn(), streamCEOConversationTurn: vi.fn(),
      createWorkRequestFromMessage: vi.fn(), createWorkRequestFromConversation: vi.fn(), createWorkGroupFromConversation: vi.fn(), proposeWorkGroupFromConversation: vi.fn(),
      listProjectWorkGroups: vi.fn().mockResolvedValue(ready([
        {
          id: 'group-current', conversation_id: 'conversation-1', parent_work_id: 'parent-1', title: 'Proyecto acordado',
          parent_status: 'INBOX', source_sha256: resultSha, consolidation_ready: false,
          consolidation: { id: 'consolidation-1', summary: 'La revisión CEO concluye que el alcance está completo.', source_sha256: resultSha, idempotency_key: 'key-1', created_by: 'ceo', created_at: '2026-10-25T11:00:00Z' },
          partial_reports: [{ id: 'partial-1', report_kind: 'PARTIAL', summary: 'Dos tareas completadas; una espera revisión.', source_sha256: resultSha, idempotency_key: 'key-2', created_by: 'ceo', created_at: '2026-10-25T10:30:00Z' }],
          children: [{ work_id: 'work-current', status: 'DONE', assigned_principal_id: 'agent-1', evidence: [],
            executions: [{ id: 'execution-current', status: 'SUCCEEDED', worker_id: 'agent-1', result_sha256: resultSha }], reviews: [] }],
        },
        {
          id: 'group-other', conversation_id: 'another-conversation', parent_work_id: 'parent-2', title: 'No pertenece a este hilo',
          parent_status: 'INBOX', source_sha256: resultSha, consolidation_ready: false, consolidation: null, partial_reports: [], children: [],
        },
      ])),
      assignWorkGroupChild: vi.fn(), confirmWorkGroupConsolidation: vi.fn(), createWorkGroupPartialReport: vi.fn(),
    };
    const onOpenBoard = setup(port);
    expect(await screen.findByText('Proyecto acordado')).toBeInTheDocument();
    expect(screen.getByText(/Se actualiza cada 15 segundos mientras este hilo está abierto/)).toBeInTheDocument();
    expect(screen.getByText(/work-current · DONE/)).toBeInTheDocument();
    expect(screen.getByText(new RegExp(`Última ejecución execution-current: SUCCEEDED · resultado SHA-256 ${resultSha}`))).toBeInTheDocument();
    expect(screen.getByText('Informe parcial CEO')).toBeInTheDocument();
    expect(screen.getByText('Dos tareas completadas; una espera revisión.')).toBeInTheDocument();
    expect(screen.getByText(/Consolidación CEO registrada/)).toBeInTheDocument();
    expect(screen.getByText('La revisión CEO concluye que el alcance está completo.')).toBeInTheDocument();
    expect(screen.queryByText('No pertenece a este hilo')).not.toBeInTheDocument();
    expect(screen.queryByText(/execution result body/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Abrir tarea work-current · DONE' }));
    expect(onOpenBoard).toHaveBeenCalledWith('project-active', 'work-current');
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
      listProjectWorkGroups: vi.fn().mockResolvedValue(ready([])), assignWorkGroupChild: vi.fn(), confirmWorkGroupConsolidation: vi.fn(), createWorkGroupPartialReport: vi.fn(),
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
      listProjectWorkGroups: vi.fn().mockResolvedValue(ready([])), assignWorkGroupChild: vi.fn(), confirmWorkGroupConsolidation: vi.fn(), createWorkGroupPartialReport: vi.fn(),
    };
    setup(port);
    await screen.findByText('Preparar el plan');
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar si quedó interrumpida' }));
    await waitFor(() => expect(port.streamCEOConversationTurn).toHaveBeenCalledWith(
      'project-active', 'conversation-1', 'Preparar el plan', pending.turn_idempotency_key, expect.any(Function),
    ));
  });

  it('reconciles a persisted pending turn until the backend records its completion', async () => {
    const pending = { ...message, turn_status: 'PENDING' as const, turn_idempotency_key: 'turn-key' };
    const completed = { ...message, id: 'reply-1', sender: 'AAO' as const, body: 'Respuesta recuperada', turn_status: 'COMPLETED' as const };
    const port: AaoConversationPort = {
      listProjectConversations: vi.fn().mockResolvedValue(ready([conversation])),
      listAssignableAgents: vi.fn().mockResolvedValue(ready([])),
      listConversationMessages: vi.fn()
        .mockResolvedValueOnce(ready([pending]))
        .mockResolvedValue(ready([pending, completed])),
      createProjectConversation: vi.fn(), appendCEOConversationMessage: vi.fn(), streamCEOConversationTurn: vi.fn(),
      createWorkRequestFromMessage: vi.fn(), createWorkRequestFromConversation: vi.fn(),
      createWorkGroupFromConversation: vi.fn(), proposeWorkGroupFromConversation: vi.fn(),
      listProjectWorkGroups: vi.fn().mockResolvedValue(ready([])), assignWorkGroupChild: vi.fn(),
      confirmWorkGroupConsolidation: vi.fn(), createWorkGroupPartialReport: vi.fn(),
    };
    setup(port);
    expect(await screen.findByRole('button', { name: 'Reintentar si quedó interrumpida' })).toBeInTheDocument();
    expect(await screen.findByText('Respuesta recuperada', {}, { timeout: 4_000 })).toBeInTheDocument();
    expect(port.listConversationMessages).toHaveBeenCalledTimes(2);
  });

  it('structures CEO-confirmed parent and dependent tasks from the conversation thread', async () => {
    const port: AaoConversationPort = {
      listProjectConversations: vi.fn().mockResolvedValue(ready([conversation])),
      listAssignableAgents: vi.fn().mockResolvedValue(ready([
        { principal_id: 'worker-1', display_name: 'Agente de implementación', competencies: ['implementación'] },
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
          tasks: [{ key: 'task-1', title: 'Investigar', description: 'Revisar fuentes', acceptance_criteria: ['Fuentes registradas'], depends_on: [], assigned_principal_id: 'worker-1' }],
        },
        based_on_message_ids: ['message-1', 'message-2'], provider: 'openai-compatible', model: 'test-model', persisted_as_work: false,
      })),
      listProjectWorkGroups: vi.fn().mockResolvedValue(ready([])), assignWorkGroupChild: vi.fn(), confirmWorkGroupConsolidation: vi.fn(), createWorkGroupPartialReport: vi.fn(),
    };
    setup(port);
    await screen.findByText('Propongo documentar los hallazgos.');
    expect(screen.queryByRole('button', { name: /Convertir en solicitud/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Proponer desglose con AAO' }));
    await screen.findByText(/AAO propuso 1 tareas a partir de 2 mensajes/);
    expect(await screen.findByText(/AAO lo sugiere según competencias declaradas/)).toBeInTheDocument();
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
      title: 'Documentar hallazgos', description: 'A partir del hilo, documentar los hallazgos acordados.', acceptance_criteria: ['Hallazgos documentados', 'CEO puede revisarlos'], due_date: null,
      tasks: [
        { key: 'task-1', title: 'Documentar hallazgos', description: 'Revisar fuentes', acceptance_criteria: ['Hallazgos documentados'], due_date: null, depends_on: [], assigned_principal_id: 'worker-1' },
        { key: 'task-2', title: 'Revisar documentación', description: '', acceptance_criteria: ['CEO puede revisarlos'], due_date: null, depends_on: ['task-1'], assigned_principal_id: 'worker-1' },
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
      listProjectWorkGroups: vi.fn().mockResolvedValue(ready([])), assignWorkGroupChild: vi.fn(), confirmWorkGroupConsolidation: vi.fn(), createWorkGroupPartialReport: vi.fn(),
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
