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
  const [streamingReply, setStreamingReply] = useState('');
  const [pendingUserMessage, setPendingUserMessage] = useState('');
  const [sendingTurn, setSendingTurn] = useState(false);
  const [requestTitle, setRequestTitle] = useState('');
  const [requestDescription, setRequestDescription] = useState('');
  const [requestCriteria, setRequestCriteria] = useState('');
  const [requestingMessageId, setRequestingMessageId] = useState(false);
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
    if (!projectId || !conversationId || !draft.trim() || sendingTurn) return;
    const message = draft.trim();
    setDraft('');
    setPendingUserMessage(message);
    setStreamingReply('');
    setSendingTurn(true);
    const result = await port.streamCEOConversationTurn(projectId, conversationId, message, (delta) => {
      setStreamingReply((current) => current + delta);
    });
    setSendingTurn(false);
    if (result.kind === 'ready') {
      setStreamingReply('');
      setPendingUserMessage('');
      setNotice('Respuesta AAO recibida y persistida. No se ha creado ni ejecutado trabajo.');
      await queryClient.invalidateQueries({ queryKey: ['office-conversation-messages', sessionId, projectId, conversationId] });
      await queryClient.invalidateQueries({ queryKey: ['office-conversations', sessionId, projectId] });
    } else {
      setStreamingReply('');
      setPendingUserMessage('');
      setDraft(message);
      setNotice(result.kind === 'error' ? `${result.code}: ${result.message}` : result.kind === 'forbidden' ? result.reason : 'No se pudo persistir el mensaje.');
      await queryClient.invalidateQueries({ queryKey: ['office-conversation-messages', sessionId, projectId, conversationId] });
      await queryClient.invalidateQueries({ queryKey: ['office-conversations', sessionId, projectId] });
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
      {message.sender === 'AAO' && message.provider && (
        <small>Proveedor: {message.provider}{message.model ? ` · modelo ${message.model}` : ''}</small>
      )}
      {message.related_work_id ? (
        <div className="office-conversation-message__work-link">
          <Button type="button" size="sm" onClick={() => onOpenBoard(projectId)}>
            Abrir trabajo {message.related_work_id}
          </Button>
          <small>Estado del trabajo: {message.work_status ?? 'desconocido'}</small>
          {message.latest_execution && (
            <small>
              Última ejecución {message.latest_execution.status} · {message.latest_execution.provider ?? 'proveedor no registrado'}
              {message.latest_execution.model ? ` / ${message.latest_execution.model}` : ''}
            </small>
          )}
        </div>
      ) : null}
    </li>
  );

  return (
    <section aria-labelledby="office-conversation-title" className="office-form-panel">
      <h3 id="office-conversation-title" className="office-form-panel__title">Conversación de proyecto (persistente)</h3>
        <p className="office-form-panel__description">
        Conversación persistente con respuesta incremental. Las tareas se estructuran explícitamente desde la conversación; hablar con AAO no admite ni ejecuta trabajo.
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
                {sendingTurn && <li className="office-conversation-message office-conversation-message--ceo"><div className="office-conversation-message__meta"><strong>CEO</strong><span>Enviando…</span></div><p className="office-conversation-message__body">{pendingUserMessage}</p></li>}
                {streamingReply && <li className="office-conversation-message office-conversation-message--aao" aria-live="polite"><div className="office-conversation-message__meta"><strong>AAO</strong><span>Respondiendo…</span></div><p className="office-conversation-message__body">{streamingReply}</p></li>}
                {messages.length === 0 && <li role="status" style={{ listStyle: 'none', color: 'var(--text-secondary)', fontSize: 12 }}>El hilo aún no tiene mensajes.</li>}
              </ol>
              <form onSubmit={sendMessage} style={{ display: 'grid', gap: 8 }}>
                <label className="office-form-field">Mensaje CEO
                  <textarea className="office-form-control office-form-control--textarea" aria-label="Mensaje CEO" required maxLength={10000} rows={3} value={draft} onChange={(event) => setDraft(event.target.value)} disabled={sendingTurn} />
                </label>
                <div><Button type="submit" disabled={!draft.trim() || sendingTurn}>{sendingTurn ? 'AAO está respondiendo…' : 'Enviar a AAO'}</Button></div>
              </form>
              <form onSubmit={(event) => {
                event.preventDefault();
                const acceptance_criteria = requestCriteria.split('\n').map((item) => item.trim()).filter(Boolean);
                if (!requestTitle.trim() || !requestDescription.trim() || acceptance_criteria.length === 0) return;
                setRequestingMessageId(true);
                void port.createWorkRequestFromConversation(projectId, conversationId, {
                  title: requestTitle.trim(), description: requestDescription.trim(), acceptance_criteria,
                }).then(async (result) => {
                  setRequestingMessageId(false);
                  if (result.kind === 'ready') {
                    setRequestTitle(''); setRequestDescription(''); setRequestCriteria('');
                    setNotice(`Tarea ${result.data.id} registrada en Entrada desde el hilo; no se ha admitido ni ejecutado.`);
                    await queryClient.invalidateQueries({ queryKey: ['board'] });
                  } else setNotice(result.kind === 'error' ? `${result.code}: ${result.message}` : result.kind === 'forbidden' ? result.reason : 'No se pudo estructurar el trabajo.');
                });
              }} className="office-conversation-work-request-form">
                <strong>Estructurar tarea a partir del hilo</strong>
                <p className="office-conversation-work-request-form__note">Resume aquí el resultado de la conversación. Revisa y confirma antes de crear una tarea en Entrada.</p>
                <label className="office-form-field">Título
                  <input className="office-form-control" aria-label="Título de tarea desde conversación" required maxLength={200} value={requestTitle} onChange={(event) => setRequestTitle(event.target.value)} />
                </label>
                <label className="office-form-field">Descripción acordada
                  <textarea className="office-form-control office-form-control--textarea" aria-label="Descripción de tarea desde conversación" required rows={3} maxLength={5000} value={requestDescription} onChange={(event) => setRequestDescription(event.target.value)} />
                </label>
                <label className="office-form-field">Criterios de aceptación (uno por línea)
                  <textarea className="office-form-control office-form-control--textarea" aria-label="Criterios de aceptación de tarea desde conversación" required rows={3} value={requestCriteria} onChange={(event) => setRequestCriteria(event.target.value)} />
                </label>
                <Button type="submit" disabled={requestingMessageId || !requestTitle.trim() || !requestDescription.trim() || !requestCriteria.trim()}>
                  {requestingMessageId ? 'Guardando…' : 'Confirmar y crear en Entrada'}
                </Button>
              </form>
            </>
          )}
        </div>
      )}
      {notice && <p role="status" aria-live="polite" style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{notice}</p>}
    </section>
  );
};
