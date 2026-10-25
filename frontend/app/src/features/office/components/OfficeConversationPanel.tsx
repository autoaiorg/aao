import React, { useEffect, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { DataState, ProjectSummary } from '../../../domain/models';
import type { AaoConversationPort, ProjectConversationMessage } from '../../../data/ports/AaoConversationPort';
import { Button } from '../../../components/ui/Button';
import './office-forms.css';

interface OfficeConversationPanelProps {
  projects: DataState<ProjectSummary[]>;
  port: AaoConversationPort;
  sessionId: string;
  onOpenBoard: (projectId: string) => void;
}

export const OfficeConversationPanel: React.FC<OfficeConversationPanelProps> = ({ projects, port, sessionId, onOpenBoard }) => {
  const queryClient = useQueryClient();
  const activeProjects = useMemo(() => projects.kind === 'ready'
    ? projects.data.filter((project) => (project.status || 'ACTIVE') === 'ACTIVE')
    : [], [projects]);
  const [projectId, setProjectId] = useState('');
  const [conversationId, setConversationId] = useState('');
  const [newTitle, setNewTitle] = useState('');
  const [draft, setDraft] = useState('');
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!activeProjects.some((project) => project.id === projectId)) {
      setProjectId(activeProjects[0]?.id || '');
      setConversationId('');
    }
  }, [activeProjects, projectId]);

  const conversationsQuery = useQuery({
    queryKey: ['office-conversations', sessionId, projectId],
    queryFn: () => port.listProjectConversations(projectId),
    enabled: !!projectId,
  });
  const conversations = conversationsQuery.data?.kind === 'ready' ? conversationsQuery.data.data : [];

  useEffect(() => {
    if (!conversations.some((item) => item.id === conversationId)) {
      setConversationId(conversations[0]?.id || '');
    }
  }, [conversations, conversationId]);

  const messagesQuery = useQuery({
    queryKey: ['office-conversation-messages', sessionId, projectId, conversationId],
    queryFn: () => port.listConversationMessages(projectId, conversationId),
    enabled: !!projectId && !!conversationId,
  });
  const messages = messagesQuery.data?.kind === 'ready' ? messagesQuery.data.data : [];

  const createConversation = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!projectId || !newTitle.trim()) return;
    const result = await port.createProjectConversation(projectId, newTitle.trim());
    if (result.kind === 'ready') {
      setConversationId(result.data.id);
      setNewTitle('');
      setNotice('Hilo persistido en el proyecto. No se ha iniciado una respuesta automática.');
      await queryClient.invalidateQueries({ queryKey: ['office-conversations', sessionId, projectId] });
    } else {
      setNotice(result.kind === 'error' ? `${result.code}: ${result.message}` : result.kind === 'forbidden' ? result.reason : 'No se pudo crear el hilo.');
    }
  };

  const sendMessage = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!projectId || !conversationId || !draft.trim()) return;
    const result = await port.appendCEOConversationMessage(projectId, conversationId, draft.trim());
    if (result.kind === 'ready') {
      setDraft('');
      setNotice('Mensaje CEO persistido. Aún no hay respuesta AAO conectada a una ejecución.');
      await queryClient.invalidateQueries({ queryKey: ['office-conversation-messages', sessionId, projectId, conversationId] });
      await queryClient.invalidateQueries({ queryKey: ['office-conversations', sessionId, projectId] });
    } else {
      setNotice(result.kind === 'error' ? `${result.code}: ${result.message}` : result.kind === 'forbidden' ? result.reason : 'No se pudo persistir el mensaje.');
    }
  };

  const stateMessage = (state: DataState<unknown> | undefined) => {
    if (!state) return 'Cargando…';
    if (state.kind === 'error') return `${state.code}: ${state.message}`;
    if (state.kind === 'forbidden') return state.reason;
    if (state.kind === 'unavailable') return state.reason;
    return null;
  };

  const renderMessage = (message: ProjectConversationMessage) => (
    <li key={message.id} className={`office-conversation-message office-conversation-message--${message.sender.toLowerCase()}`}>
      <div className="office-conversation-message__meta">
        <strong>{message.sender}</strong><time dateTime={message.created_at}>{new Date(message.created_at).toLocaleString()}</time>
      </div>
      <p className="office-conversation-message__body">{message.body}</p>
      {message.related_work_id && <button type="button" onClick={() => onOpenBoard(projectId)} style={{ marginTop: 6 }}>Trabajo {message.related_work_id}</button>}
    </li>
  );

  return (
    <section aria-labelledby="office-conversation-title" className="office-form-panel">
      <h3 id="office-conversation-title" className="office-form-panel__title">Conversación de proyecto (persistente)</h3>
      <p className="office-form-panel__description">
        Los mensajes se guardan en AAO. Este incremento no genera respuestas ni ejecuta instrucciones; las órdenes de trabajo deben registrarse explícitamente en Entrada.
      </p>
      {projects.kind !== 'ready' ? (
        <p role="status">{projects.kind === 'error' ? projects.message : projects.kind === 'forbidden' ? projects.reason : 'Proyectos LIVE no disponibles.'}</p>
      ) : activeProjects.length === 0 ? (
        <p role="status">No hay proyectos activos para iniciar una conversación.</p>
      ) : (
        <div className="office-conversation-content">
          <label className="office-form-field office-conversation-project">Proyecto activo
            <select className="office-form-control" aria-label="Proyecto de conversación" value={projectId} onChange={(event) => { setProjectId(event.target.value); setConversationId(''); }}>
              {activeProjects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
            </select>
          </label>
          <form onSubmit={createConversation} className="office-conversation-create">
            <label className="office-form-field">Nuevo hilo
              <input className="office-form-control" aria-label="Título de conversación" required maxLength={200} value={newTitle} onChange={(event) => setNewTitle(event.target.value)} />
            </label>
            <Button type="submit" disabled={!newTitle.trim()}>Crear hilo</Button>
          </form>
          {conversations.length > 0 && (
            <label className="office-form-field office-conversation-project">Hilo guardado
              <select className="office-form-control" aria-label="Hilo guardado" value={conversationId} onChange={(event) => setConversationId(event.target.value)}>
                {conversations.map((conversation) => <option key={conversation.id} value={conversation.id}>{conversation.title}</option>)}
              </select>
            </label>
          )}
          {conversationsQuery.isLoading && <p role="status">Cargando conversaciones…</p>}
          {conversationsQuery.data && conversationsQuery.data.kind !== 'ready' && <p role="alert">{stateMessage(conversationsQuery.data)}</p>}
          {conversationId && (
            <>
              {messagesQuery.isLoading && <p role="status">Cargando mensajes…</p>}
              {messagesQuery.data && messagesQuery.data.kind !== 'ready' && <p role="alert">{stateMessage(messagesQuery.data)}</p>}
              <ol aria-label="Mensajes de la conversación" className="office-conversation-list">
                {messages.map(renderMessage)}
                {messages.length === 0 && <li role="status" style={{ listStyle: 'none', color: 'var(--text-secondary)', fontSize: 12 }}>El hilo aún no tiene mensajes.</li>}
              </ol>
              <form onSubmit={sendMessage} style={{ display: 'grid', gap: 8 }}>
                <label className="office-form-field">Mensaje CEO
                  <textarea className="office-form-control office-form-control--textarea" aria-label="Mensaje CEO" required maxLength={10000} rows={3} value={draft} onChange={(event) => setDraft(event.target.value)} />
                </label>
                <div><Button type="submit" disabled={!draft.trim()}>Guardar mensaje</Button></div>
              </form>
            </>
          )}
        </div>
      )}
      {notice && <p role="status" aria-live="polite" style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{notice}</p>}
    </section>
  );
};
