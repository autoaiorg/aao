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
const message = { id: 'message-1', sender: 'CEO' as const, body: 'Preparar el plan', related_work_id: null, created_at: '2026-10-25T10:00:00Z' };
const ready = <T,>(data: T): DataState<T> => ({ kind: 'ready', origin: 'live', fetchedAt: 'now', data });

function setup(port: AaoConversationPort) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><OfficeConversationPanel projects={projects} port={port} sessionId="session-a" onOpenBoard={vi.fn()} /></QueryClientProvider>);
}

describe('office persistent project conversation', () => {
  it('persists CEO messages and shows only server-returned messages without inventing an AAO reply', async () => {
    const port: AaoConversationPort = {
      listProjectConversations: vi.fn().mockResolvedValue(ready([conversation])),
      listConversationMessages: vi.fn().mockResolvedValue(ready([message])),
      createProjectConversation: vi.fn(),
      appendCEOConversationMessage: vi.fn().mockResolvedValue(ready(message)),
    };
    setup(port);
    await screen.findByText('Preparar el plan');
    fireEvent.change(screen.getByLabelText('Mensaje CEO'), { target: { value: 'Revisar el presupuesto' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar mensaje' }));
    await waitFor(() => expect(port.appendCEOConversationMessage).toHaveBeenCalledWith('project-active', 'conversation-1', 'Revisar el presupuesto'));
    expect(screen.getByText(/Aún no hay respuesta AAO conectada/)).toBeInTheDocument();
    expect(screen.queryByText('AAO')).not.toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Proyecto pausado' })).not.toBeInTheDocument();
  });
});
