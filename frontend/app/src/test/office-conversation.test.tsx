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
      createWorkRequestFromConversation: vi.fn(),
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

  it('structures a CEO-confirmed task from the conversation thread, not an individual message', async () => {
    const port: AaoConversationPort = {
      listProjectConversations: vi.fn().mockResolvedValue(ready([conversation])),
      listConversationMessages: vi.fn().mockResolvedValue(ready([message, { ...message, id: 'message-2', sender: 'AAO', body: 'Propongo documentar los hallazgos.' } ])),
      createProjectConversation: vi.fn(), appendCEOConversationMessage: vi.fn(), streamCEOConversationTurn: vi.fn(),
      createWorkRequestFromMessage: vi.fn(),
      createWorkRequestFromConversation: vi.fn().mockResolvedValue(ready({ id: 'work-1', status: 'INBOX', created: true })),
    };
    setup(port);
    await screen.findByText('Propongo documentar los hallazgos.');
    expect(screen.queryByRole('button', { name: /Convertir en solicitud/ })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Título de tarea desde conversación'), { target: { value: 'Documentar hallazgos' } });
    fireEvent.change(screen.getByLabelText('Descripción de tarea desde conversación'), { target: { value: 'A partir del hilo, documentar los hallazgos acordados.' } });
    fireEvent.change(screen.getByLabelText('Criterios de aceptación de tarea desde conversación'), { target: { value: 'Hallazgos documentados\nCEO puede revisarlos' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar y crear en Entrada' }));
    await waitFor(() => expect(port.createWorkRequestFromConversation).toHaveBeenCalledWith('project-active', 'conversation-1', {
      title: 'Documentar hallazgos', description: 'A partir del hilo, documentar los hallazgos acordados.', acceptance_criteria: ['Hallazgos documentados', 'CEO puede revisarlos'],
    }));
    expect(await screen.findByText(/no se ha admitido ni ejecutado/)).toBeInTheDocument();
    expect(port.createWorkRequestFromMessage).not.toHaveBeenCalled();
  });
});
