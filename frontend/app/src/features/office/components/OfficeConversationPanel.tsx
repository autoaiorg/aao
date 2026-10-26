import React, { useEffect, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { DataState, ProjectSummary } from '../../../domain/models';
import type { AaoConversationPort, ProjectConversationMessage, ProjectWorkGroup } from '../../../data/ports/AaoConversationPort';
import { Button } from '../../../components/ui/Button';
import './office-forms.css';

interface OfficeConversationPanelProps {
  projects: DataState<ProjectSummary[]>;
  port: AaoConversationPort;
  sessionId: string;
  onOpenBoard: (projectId: string, workId?: string) => void;
}

interface WorkTaskDraft {
  key: string;
  title: string;
  description: string;
  acceptanceCriteria: string;
  dependsOn: string[];
  assignedPrincipalId: string;
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
  const [turnIdempotencyKey, setTurnIdempotencyKey] = useState('');
  const [requestTitle, setRequestTitle] = useState('');
  const [requestDescription, setRequestDescription] = useState('');
  const [requestCriteria, setRequestCriteria] = useState('');
  const [requestingMessageId, setRequestingMessageId] = useState(false);
  const [proposingWorkGroup, setProposingWorkGroup] = useState(false);
  const [proposalGenerated, setProposalGenerated] = useState(false);
  const [proposalSourceMessageIds, setProposalSourceMessageIds] = useState<string[] | null>(null);
  const [workTasks, setWorkTasks] = useState<WorkTaskDraft[]>([{ key: 'task-1', title: '', description: '', acceptanceCriteria: '', dependsOn: [], assignedPrincipalId: '' }]);
  const [nextTaskNumber, setNextTaskNumber] = useState(2);
  const [workGroupIdempotencyKey, setWorkGroupIdempotencyKey] = useState('');
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
  const workGroupsQuery = useQuery({
    queryKey: ['office-conversation-work-groups', sessionId, projectId, conversationId],
    queryFn: () => port.listProjectWorkGroups(projectId),
    enabled: !!projectId && !!conversationId,
    refetchInterval: 15_000,
  });
  const conversationWorkGroups = workGroupsQuery.data?.kind === 'ready'
    ? workGroupsQuery.data.data.filter((group) => group.conversation_id === conversationId)
    : [];
  const assignableAgentsQuery = useQuery({
    queryKey: ['office-assignable-agents', sessionId, projectId],
    queryFn: () => port.listAssignableAgents(projectId),
    enabled: !!projectId,
  });
  const assignableAgents = assignableAgentsQuery.data?.kind === 'ready' ? assignableAgentsQuery.data.data : [];

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
    if (proposalGenerated) {
      setRequestTitle(''); setRequestDescription(''); setRequestCriteria('');
      setWorkTasks([{ key: 'task-1', title: '', description: '', acceptanceCriteria: '', dependsOn: [], assignedPrincipalId: '' }]);
      setNextTaskNumber(2); setWorkGroupIdempotencyKey(''); setProposalGenerated(false); setProposalSourceMessageIds(null);
    }
    const idempotencyKey = turnIdempotencyKey || crypto.randomUUID();
    setTurnIdempotencyKey(idempotencyKey);
    const result = await port.streamCEOConversationTurn(projectId, conversationId, message, idempotencyKey, (delta) => {
      setStreamingReply((current) => current + delta);
    });
    setSendingTurn(false);
    if (result.kind === 'ready') {
      setStreamingReply('');
      setPendingUserMessage('');
      setTurnIdempotencyKey('');
      setNotice('Respuesta AAO recibida y persistida. Revisa de nuevo el desglose tras continuar la conversación; no se ha creado ni ejecutado trabajo.');
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

  const retryPendingTurn = async (message: ProjectConversationMessage) => {
    if (!projectId || !conversationId || sendingTurn || !message.turn_idempotency_key) return;
    setPendingUserMessage(message.body);
    setStreamingReply('');
    setSendingTurn(true);
    const result = await port.streamCEOConversationTurn(
      projectId, conversationId, message.body, message.turn_idempotency_key,
      (delta) => setStreamingReply((current) => current + delta),
    );
    setSendingTurn(false);
    setPendingUserMessage('');
    setStreamingReply('');
    setNotice(result.kind === 'ready'
      ? 'Respuesta recuperada y persistida.'
      : result.kind === 'error' ? `${result.code}: ${result.message}`
        : result.kind === 'forbidden' ? result.reason : 'No se pudo recuperar la respuesta.');
    await queryClient.invalidateQueries({ queryKey: ['office-conversation-messages', sessionId, projectId, conversationId] });
  };

  const stateMessage = (state: DataState<unknown> | undefined) => {
    if (!state) return 'Cargando…';
    if (state.kind === 'error') return `${state.code}: ${state.message}`;
    if (state.kind === 'forbidden') return state.reason;
    if (state.kind === 'unavailable') return state.reason;
    return null;
  };

  const updateWorkTask = (key: string, update: Partial<WorkTaskDraft>) => {
    setWorkGroupIdempotencyKey('');
    setWorkTasks((current) => current.map((task) => task.key === key ? { ...task, ...update } : task));
  };

  const submitWorkGroup = async (event: React.FormEvent) => {
    event.preventDefault();
    const criteria = requestCriteria.split('\n').map((item) => item.trim()).filter(Boolean);
    const tasks = workTasks.map((task) => ({
      key: task.key,
      title: task.title.trim(),
      description: task.description.trim(),
      acceptance_criteria: task.acceptanceCriteria.split('\n').map((item) => item.trim()).filter(Boolean),
      depends_on: task.dependsOn,
      ...(task.assignedPrincipalId ? { assigned_principal_id: task.assignedPrincipalId } : {}),
    }));
    if (!projectId || !conversationId || !requestTitle.trim() || !requestDescription.trim()
      || criteria.length === 0 || tasks.some((task) => !task.title || task.acceptance_criteria.length === 0)) return;
    const idempotencyKey = workGroupIdempotencyKey || crypto.randomUUID();
    setWorkGroupIdempotencyKey(idempotencyKey);
    setRequestingMessageId(true);
    const result = await port.createWorkGroupFromConversation(projectId, conversationId, {
      idempotency_key: idempotencyKey,
      title: requestTitle.trim(), description: requestDescription.trim(),
      acceptance_criteria: criteria, tasks,
      ...(proposalSourceMessageIds ? { based_on_message_ids: proposalSourceMessageIds } : {}),
    });
    setRequestingMessageId(false);
    if (result.kind === 'ready') {
      setRequestTitle(''); setRequestDescription(''); setRequestCriteria('');
      setWorkTasks([{ key: 'task-1', title: '', description: '', acceptanceCriteria: '', dependsOn: [], assignedPrincipalId: '' }]);
      setNextTaskNumber(2); setWorkGroupIdempotencyKey(''); setProposalGenerated(false); setProposalSourceMessageIds(null);
      setNotice(`Desglose ${result.data.id} (${result.data.tasks.length} tareas) registrado en Entrada; no se ha admitido ni ejecutado.`);
      await queryClient.invalidateQueries({ queryKey: ['board'] });
      await queryClient.invalidateQueries({ queryKey: ['office-conversation-work-groups', sessionId, projectId, conversationId] });
    } else {
      setNotice(result.kind === 'error' ? `${result.code}: ${result.message}` : result.kind === 'forbidden' ? result.reason : 'No se pudo estructurar el desglose.');
    }
  };

  const proposeWorkGroup = async () => {
    if (!projectId || !conversationId || proposingWorkGroup || sendingTurn) return;
    setProposingWorkGroup(true);
    const result = await port.proposeWorkGroupFromConversation(projectId, conversationId);
    setProposingWorkGroup(false);
    if (result.kind === 'ready') {
      const proposal = result.data.proposal;
      setRequestTitle(proposal.title);
      setRequestDescription(proposal.description);
      setRequestCriteria(proposal.acceptance_criteria.join('\n'));
      setWorkTasks(proposal.tasks.map((task) => ({
        key: task.key,
        title: task.title,
        description: task.description,
        acceptanceCriteria: task.acceptance_criteria.join('\n'),
        dependsOn: task.depends_on,
        assignedPrincipalId: '',
      })));
      setNextTaskNumber(proposal.tasks.length + 1);
      setWorkGroupIdempotencyKey('');
      setProposalGenerated(true);
      setProposalSourceMessageIds(result.data.based_on_message_ids);
      setNotice(`AAO propuso ${proposal.tasks.length} tareas a partir de ${result.data.based_on_message_ids.length} mensajes (${result.data.provider}${result.data.model ? ` / ${result.data.model}` : ''}). Revísalas y edítalas antes de confirmar.`);
    } else {
      setNotice(result.kind === 'error' ? `${result.code}: ${result.message}` : result.kind === 'forbidden' ? result.reason : 'No se pudo proponer el desglose desde la conversación.');
    }
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
      {message.turn_status === 'FAILED' && <p role="alert">La respuesta de AAO falló ({message.turn_error_code ?? 'ERROR'}). Puedes reenviar el mensaje para reintentar.</p>}
      {message.turn_status === 'PENDING' && (
        <div role="status">
          <span>AAO está procesando esta respuesta.</span>{' '}
          <Button type="button" variant="secondary" size="sm" disabled={sendingTurn || !message.turn_idempotency_key}
            onClick={() => void retryPendingTurn(message)}>
            Reintentar si quedó interrumpida
          </Button>
        </div>
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
            <select className="office-form-control" aria-label="Proyecto de conversación" value={projectId} onChange={(event) => { setProjectId(event.target.value); setConversationId(''); setProposalGenerated(false); setProposalSourceMessageIds(null); }}>
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
              <select className="office-form-control" aria-label="Hilo guardado" value={conversationId} onChange={(event) => { setConversationId(event.target.value); setProposalGenerated(false); setProposalSourceMessageIds(null); }}>
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
              <section className="office-conversation-work-status" aria-labelledby="office-conversation-work-status-title">
                <div className="office-form-panel__header">
                  <div>
                    <h4 id="office-conversation-work-status-title">Trabajo estructurado desde este hilo</h4>
                    <p>Estado del motor AAO. Se actualiza cada 15 segundos mientras este hilo está abierto; consultar aquí no admite ni ejecuta tareas.</p>
                  </div>
                  <Button type="button" variant="secondary" size="sm" onClick={() => void workGroupsQuery.refetch()} disabled={workGroupsQuery.isFetching}>
                    {workGroupsQuery.isFetching ? 'Actualizando…' : 'Actualizar estado'}
                  </Button>
                </div>
                {workGroupsQuery.data?.kind === 'error' && <p role="alert">{workGroupsQuery.data.code}: {workGroupsQuery.data.message}</p>}
                {workGroupsQuery.data?.kind === 'forbidden' && <p role="alert">{workGroupsQuery.data.reason}</p>}
                {workGroupsQuery.data?.kind === 'unavailable' && <p role="alert">{workGroupsQuery.data.reason}</p>}
                {workGroupsQuery.isLoading && <p role="status">Consultando grupos persistidos…</p>}
                {workGroupsQuery.data?.kind === 'ready' && conversationWorkGroups.length === 0 && <p>No hay desglose confirmado desde este hilo.</p>}
                {conversationWorkGroups.map((group: ProjectWorkGroup) => (
                  <article className="office-conversation-work-status__group" key={group.id}>
                    <div className="office-conversation-work-status__heading">
                      <strong>{group.title}</strong><span>Grupo {group.id} · {group.parent_status}</span>
                    </div>
                    <Button type="button" variant="secondary" size="sm" onClick={() => onOpenBoard(projectId, group.parent_work_id)}>
                      Abrir encargo padre
                    </Button>
                    <ul aria-label={`Estado de tareas: ${group.title}`}>
                      {group.children.map((child) => {
                        const latestExecution = child.executions[child.executions.length - 1];
                        return <li key={child.work_id}>
                          <Button type="button" variant="secondary" size="sm" onClick={() => onOpenBoard(projectId, child.work_id)}>
                            Abrir tarea {child.work_id} · {child.status}
                          </Button>
                          {child.assigned_principal_id && <small>Asignado a {child.assigned_principal_id}</small>}
                          {latestExecution && <small>Última ejecución {latestExecution.id}: {latestExecution.status}{latestExecution.result_sha256 ? ` · resultado SHA-256 ${latestExecution.result_sha256}` : ''}</small>}
                        </li>;
                      })}
                    </ul>
                    {group.consolidation && <p>Consolidación CEO registrada · {group.consolidation.created_at}</p>}
                  </article>
                ))}
              </section>
              <form onSubmit={sendMessage} style={{ display: 'grid', gap: 8 }}>
                <label className="office-form-field">Mensaje CEO
                  <textarea className="office-form-control office-form-control--textarea" aria-label="Mensaje CEO" required maxLength={10000} rows={3} value={draft} onChange={(event) => { setDraft(event.target.value); setTurnIdempotencyKey(''); }} disabled={sendingTurn} />
                </label>
                <div><Button type="submit" disabled={!draft.trim() || sendingTurn}>{sendingTurn ? 'AAO está respondiendo…' : 'Enviar a AAO'}</Button></div>
              </form>
              <form onSubmit={(event) => void submitWorkGroup(event)} className="office-conversation-work-request-form">
                <strong>Estructurar tareas a partir del hilo</strong>
                <p className="office-conversation-work-request-form__note">Pide a AAO una propuesta basada en todo el hilo, revísala y edítala. Solo al confirmarla se guarda como trabajo canónico en Entrada; no se admite ni ejecuta automáticamente.</p>
                <Button type="button" variant="secondary" onClick={() => void proposeWorkGroup()} disabled={proposingWorkGroup || sendingTurn || messages.length === 0}>
                  {proposingWorkGroup ? 'AAO está estructurando el hilo…' : 'Proponer desglose con AAO'}
                </Button>
                <label className="office-form-field">Título
                  <input className="office-form-control" aria-label="Título de tarea desde conversación" required maxLength={200} value={requestTitle} onChange={(event) => { setWorkGroupIdempotencyKey(''); setRequestTitle(event.target.value); }} />
                </label>
                <label className="office-form-field">Descripción acordada
                  <textarea className="office-form-control office-form-control--textarea" aria-label="Descripción de tarea desde conversación" required rows={3} maxLength={5000} value={requestDescription} onChange={(event) => { setWorkGroupIdempotencyKey(''); setRequestDescription(event.target.value); }} />
                </label>
                <label className="office-form-field">Criterios de aceptación (uno por línea)
                  <textarea className="office-form-control office-form-control--textarea" aria-label="Criterios de aceptación de tarea desde conversación" required rows={3} value={requestCriteria} onChange={(event) => { setWorkGroupIdempotencyKey(''); setRequestCriteria(event.target.value); }} />
                </label>
                <div className="office-conversation-task-list">
                  <strong>Tareas del desglose</strong>
                  {assignableAgentsQuery.isLoading && <p role="status">Cargando identidades autorizadas para este proyecto…</p>}
                  {assignableAgentsQuery.data && assignableAgentsQuery.data.kind !== 'ready' && (
                    <p role="alert">No se pudieron cargar identidades asignables: {stateMessage(assignableAgentsQuery.data)}</p>
                  )}
                  {workTasks.map((task, index) => (
                    <fieldset key={task.key} className="office-conversation-task">
                      <legend>{task.key}</legend>
                      <label className="office-form-field">Título de tarea
                        <input className="office-form-control" aria-label={`Título ${task.key}`} required maxLength={200} value={task.title} onChange={(event) => updateWorkTask(task.key, { title: event.target.value })} />
                      </label>
                      <label className="office-form-field">Descripción
                        <textarea className="office-form-control office-form-control--textarea" aria-label={`Descripción ${task.key}`} rows={2} maxLength={5000} value={task.description} onChange={(event) => updateWorkTask(task.key, { description: event.target.value })} />
                      </label>
                      <label className="office-form-field">Criterios (uno por línea)
                        <textarea className="office-form-control office-form-control--textarea" aria-label={`Criterios ${task.key}`} required rows={2} value={task.acceptanceCriteria} onChange={(event) => updateWorkTask(task.key, { acceptanceCriteria: event.target.value })} />
                      </label>
                      <label className="office-form-field">Asignar a identidad autorizada (opcional)
                        <select className="office-form-control" aria-label={`Asignar ${task.key}`} value={task.assignedPrincipalId}
                          onChange={(event) => updateWorkTask(task.key, { assignedPrincipalId: event.target.value })}>
                          <option value="">Sin asignar</option>
                          {assignableAgents.map((agent) => <option key={agent.principal_id} value={agent.principal_id}>
                            {agent.display_name} ({agent.principal_id})
                          </option>)}
                        </select>
                      </label>
                      {index > 0 && (
                        <fieldset className="office-conversation-dependencies">
                          <legend>Depende de estas tareas anteriores (opcional)</legend>
                          {workTasks.slice(0, index).map((previous) => (
                            <label key={previous.key}>
                              <input type="checkbox" checked={task.dependsOn.includes(previous.key)} onChange={(event) => updateWorkTask(task.key, {
                                dependsOn: event.target.checked
                                  ? [...task.dependsOn, previous.key]
                                  : task.dependsOn.filter((key) => key !== previous.key),
                              })} />
                              {previous.key}: {previous.title || 'tarea sin título'}
                            </label>
                          ))}
                        </fieldset>
                      )}
                      {workTasks.length > 1 && <Button type="button" variant="secondary" onClick={() => { setWorkGroupIdempotencyKey(''); setWorkTasks((current) => current.filter((item) => item.key !== task.key).map((item) => ({ ...item, dependsOn: item.dependsOn.filter((key) => key !== task.key) }))); }}>Eliminar {task.key}</Button>}
                    </fieldset>
                  ))}
                  <Button type="button" variant="secondary" onClick={() => {
                    const key = `task-${nextTaskNumber}`;
                    setNextTaskNumber((number) => number + 1);
                    setWorkGroupIdempotencyKey('');
                    setWorkTasks((current) => [...current, { key, title: '', description: '', acceptanceCriteria: '', dependsOn: [], assignedPrincipalId: '' }]);
                  }}>Añadir tarea</Button>
                </div>
                <Button type="submit" disabled={requestingMessageId || !requestTitle.trim() || !requestDescription.trim() || !requestCriteria.trim() || workTasks.some((task) => !task.title.trim() || !task.acceptanceCriteria.trim())}>
                  {requestingMessageId ? 'Guardando…' : 'Confirmar desglose y crear en Entrada'}
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
