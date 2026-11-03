import React, { useMemo, useState } from 'react';
import type { AgentIdentity, DataState, OrgUnit } from '../../../domain/models';
import type {
  OrganizationProfileCommand,
  OrganizationUnitCommand,
} from '../../../data/ports/AaoOrganizationCommandPort';
import {
  type ProposedProfileDraft,
  type ProposedUnitDraft,
  validateConstitutionProposal,
} from './enterpriseProjection';

export interface OrganizationConstitutionCenterProps {
  persistedUnits: OrgUnit[];
  agents: AgentIdentity[];
  historicalAgentCount: number;
  unassignedAgentsCount: number;
  registeredProfilesCount: number;
  isDemo: boolean;
  canManageOrganization: boolean;
  onSaveUnit?: (input: OrganizationUnitCommand) => Promise<DataState<unknown>>;
  onSaveProfile?: (input: OrganizationProfileCommand) => Promise<DataState<unknown>>;
  onRefresh?: () => void;
}

export const OrganizationConstitutionCenter: React.FC<OrganizationConstitutionCenterProps> = ({
  persistedUnits,
  agents,
  historicalAgentCount,
  unassignedAgentsCount,
  registeredProfilesCount,
  isDemo,
  canManageOrganization,
  onSaveUnit,
  onSaveProfile,
  onRefresh,
}) => {
  const declaredUnits = useMemo(
    () => persistedUnits.filter((u) => u.id !== 'unit-unassigned'),
    [persistedUnits]
  );

  // Local Staging State (Step 2: Propuesta Local No Persistida)
  const [draftUnits, setDraftUnits] = useState<ProposedUnitDraft[]>([]);
  const [draftProfiles, setDraftProfiles] = useState<ProposedProfileDraft[]>([]);

  // Form inputs for adding a unit draft
  const [unitId, setUnitId] = useState('');
  const [unitCode, setUnitCode] = useState('');
  const [unitName, setUnitName] = useState('');
  const [parentId, setParentId] = useState('');
  const [leadRole, setLeadRole] = useState('');
  const [leadPrincipalId, setLeadPrincipalId] = useState('');
  const [description, setDescription] = useState('');

  // Form inputs for adding a profile draft
  const [principalId, setPrincipalId] = useState('');
  const [profileUnitId, setProfileUnitId] = useState('');
  const [roleTitle, setRoleTitle] = useState('');
  const [managerPrincipalId, setManagerPrincipalId] = useState('');
  const [competenciesText, setCompetenciesText] = useState('');

  // Execution feedback (Step 4)
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [executionLogs, setExecutionLogs] = useState<
    Array<{ kind: 'success' | 'error' | 'info'; message: string }>
  >([]);

  const validation = useMemo(
    () =>
      validateConstitutionProposal({
        persistedUnits: declaredUnits,
        draftUnits,
        draftProfiles,
        canManageOrganization,
        isDemo,
      }),
    [declaredUnits, draftUnits, draftProfiles, canManageOrganization, isDemo]
  );

  const availableUnitsForProfile = useMemo(() => {
    const map = new Map<string, { id: string; code: string; name: string; source: 'PERSISTED' | 'DRAFT' }>();
    for (const u of declaredUnits) {
      map.set(u.id, { id: u.id, code: u.code, name: u.name, source: 'PERSISTED' });
    }
    for (const d of draftUnits) {
      if (d.id.trim()) {
        map.set(d.id.trim(), {
          id: d.id.trim(),
          code: d.code.trim() || 'BORRADOR',
          name: d.name.trim() || d.id.trim(),
          source: 'DRAFT',
        });
      }
    }
    return Array.from(map.values());
  }, [declaredUnits, draftUnits]);

  const handleStageUnitDraft = (e: React.FormEvent) => {
    e.preventDefault();
    if (!unitId.trim() && !unitName.trim()) return;
    const nextDraft: ProposedUnitDraft = {
      draftId: `draft-unit-${Date.now()}-${draftUnits.length + 1}`,
      id: unitId.trim(),
      code: unitCode.trim().toUpperCase(),
      name: unitName.trim(),
      parent_id: parentId.trim() || null,
      leadRole: leadRole.trim(),
      lead_principal_id: leadPrincipalId.trim() || null,
      description: description.trim(),
      enabled: true,
    };
    setDraftUnits((prev) => [...prev, nextDraft]);
    if (!profileUnitId && nextDraft.id) {
      setProfileUnitId(nextDraft.id);
    }
    setUnitId('');
    setUnitCode('');
    setUnitName('');
    setParentId('');
    setLeadRole('');
    setLeadPrincipalId('');
    setDescription('');
  };

  const handleStageProfileDraft = (e: React.FormEvent) => {
    e.preventDefault();
    if (!principalId.trim() && !roleTitle.trim()) return;
    const nextProfile: ProposedProfileDraft = {
      draftId: `draft-profile-${Date.now()}-${draftProfiles.length + 1}`,
      principal_id: principalId.trim(),
      display_name: principalId.trim(),
      unit_id: profileUnitId.trim() || null,
      role_title: roleTitle.trim(),
      manager_principal_id: managerPrincipalId.trim() || null,
      competencies: competenciesText
        .split(',')
        .map((c) => c.trim())
        .filter(Boolean),
      enabled: true,
    };
    setDraftProfiles((prev) => [...prev, nextProfile]);
    setPrincipalId('');
    setRoleTitle('');
    setManagerPrincipalId('');
    setCompetenciesText('');
  };

  const handleRemoveUnitDraft = (draftId: string) => {
    setDraftUnits((prev) => prev.filter((u) => u.draftId !== draftId));
  };

  const handleRemoveProfileDraft = (draftId: string) => {
    setDraftProfiles((prev) => prev.filter((p) => p.draftId !== draftId));
  };

  const handleExecuteAuthorizedConstitution = async () => {
    if (!validation.canSubmitAuthorized || !onSaveUnit || !onSaveProfile) return;
    setIsSubmitting(true);
    const logs: Array<{ kind: 'success' | 'error' | 'info'; message: string }> = [];

    try {
      for (const unitDraft of draftUnits) {
        const res = await onSaveUnit({
          id: unitDraft.id,
          code: unitDraft.code,
          name: unitDraft.name,
          parent_id: unitDraft.parent_id,
          lead_principal_id: unitDraft.lead_principal_id,
          enabled: true,
        });
        if (res.kind === 'ready') {
          logs.push({
            kind: 'success',
            message: `PUT /v1/organization/units → Unidad «${unitDraft.name}» (${unitDraft.code}) persistida en el backend.`,
          });
        } else {
          const reason = 'reason' in res ? res.reason : 'Operación rechazada por el backend.';
          logs.push({
            kind: 'error',
            message: `Error al registrar unidad «${unitDraft.id}»: ${reason}`,
          });
          setExecutionLogs(logs);
          setIsSubmitting(false);
          return;
        }
      }

      for (const profDraft of draftProfiles) {
        const res = await onSaveProfile({
          principal_id: profDraft.principal_id,
          display_name: profDraft.display_name,
          unit_id: profDraft.unit_id,
          role_title: profDraft.role_title,
          manager_principal_id: profDraft.manager_principal_id,
          competencies: profDraft.competencies,
          enabled: true,
        });
        if (res.kind === 'ready') {
          logs.push({
            kind: 'success',
            message: `PUT /v1/organization/profiles → Perfil de «${profDraft.principal_id}» adscrito a «${profDraft.unit_id}» (${profDraft.role_title}).`,
          });
        } else {
          const reason = 'reason' in res ? res.reason : 'Operación rechazada por el backend.';
          logs.push({
            kind: 'error',
            message: `Error al registrar perfil «${profDraft.principal_id}»: ${reason}`,
          });
          setExecutionLogs(logs);
          setIsSubmitting(false);
          return;
        }
      }

      setDraftUnits([]);
      setDraftProfiles([]);
      if (onRefresh) {
        onRefresh();
        logs.push({
          kind: 'info',
          message:
            'Paso 5 ejecutado: Solicitud GET /v1/organization emitida para reconstruir la Oficina LIVE exclusivamente desde datos persistidos.',
        });
      }
      setExecutionLogs(logs);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      data-testid="organization-constitution-center"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '14px',
        color: '#e2e8f0',
        fontSize: '12px',
      }}
    >
      {/* Header Banner: Persisted vs Proposed Separation */}
      <div
        style={{
          padding: '12px 14px',
          borderRadius: '10px',
          background: 'rgba(15, 23, 42, 0.92)',
          border: '1px solid rgba(56, 189, 248, 0.35)',
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
          <div>
            <strong style={{ fontSize: '14px', color: '#f8fafc', display: 'block' }}>
              ⚖️ Centro de Constitución Organizativa (Flujo Gobernado en 5 Pasos)
            </strong>
            <span style={{ color: '#94a3b8', fontSize: '11px' }}>
              Separa estrictamente la estructura persistida en PostgreSQL, la proyección operativa actual y el borrador local de propuesta.
            </span>
          </div>
          <span
            style={{
              padding: '3px 9px',
              borderRadius: '999px',
              fontSize: '10px',
              fontWeight: 800,
              background: isDemo
                ? 'rgba(245, 158, 11, 0.2)'
                : canManageOrganization
                ? 'rgba(16, 185, 129, 0.2)'
                : 'rgba(239, 68, 68, 0.2)',
              color: isDemo ? '#fcd34d' : canManageOrganization ? '#6ee7b7' : '#fca5a5',
              border: '1px solid currentColor',
            }}
          >
            {isDemo
              ? 'DEMO · SOLO SIMULACIÓN LOCAL'
              : canManageOrganization
              ? 'LIVE · AUTORIDAD CEO ACTIVA'
              : 'LIVE · SOLO LECTURA (REQUIERE SESIÓN CEO)'}
          </span>
        </div>

        {/* Step 1 Diagnostic Counters */}
        <div
          data-testid="constitution-step1-counters"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
            gap: '8px',
            marginTop: '4px',
          }}
        >
          <div style={{ padding: '8px 10px', borderRadius: '8px', background: 'rgba(2, 6, 23, 0.65)', border: '1px solid rgba(148, 163, 184, 0.2)' }}>
            <div style={{ fontSize: '10px', color: '#94a3b8', textTransform: 'uppercase' }}>Unidades declaradas</div>
            <strong data-testid="counter-declared-units" style={{ fontSize: '16px', color: '#f8fafc' }}>
              {declaredUnits.length}
            </strong>
          </div>
          <div style={{ padding: '8px 10px', borderRadius: '8px', background: 'rgba(2, 6, 23, 0.65)', border: '1px solid rgba(148, 163, 184, 0.2)' }}>
            <div style={{ fontSize: '10px', color: '#94a3b8', textTransform: 'uppercase' }}>Perfiles registrados</div>
            <strong data-testid="counter-registered-profiles" style={{ fontSize: '16px', color: '#38bdf8' }}>
              {registeredProfilesCount}
            </strong>
          </div>
          <div style={{ padding: '8px 10px', borderRadius: '8px', background: 'rgba(2, 6, 23, 0.65)', border: '1px solid rgba(148, 163, 184, 0.2)' }}>
            <div style={{ fontSize: '10px', color: '#94a3b8', textTransform: 'uppercase' }}>Principales activos / sin unidad</div>
            <strong data-testid="counter-active-agents" style={{ fontSize: '16px', color: '#a7f3d0' }}>
              {agents.length} / {unassignedAgentsCount}
            </strong>
          </div>
          <div style={{ padding: '8px 10px', borderRadius: '8px', background: 'rgba(2, 6, 23, 0.65)', border: '1px solid rgba(245, 158, 11, 0.3)' }}>
            <div style={{ fontSize: '10px', color: '#fcd34d', textTransform: 'uppercase' }}>Principales históricos (credencial deshabilitada)</div>
            <strong data-testid="counter-historical-principals" style={{ fontSize: '16px', color: '#fde68a' }}>
              {historicalAgentCount}
            </strong>
          </div>
        </div>
      </div>

      {/* Step 1: Inspect Authorized Structure */}
      <section
        style={{
          padding: '12px 14px',
          borderRadius: '10px',
          background: 'rgba(15, 23, 42, 0.78)',
          border: '1px solid rgba(148, 163, 184, 0.2)',
        }}
      >
        <div style={{ fontWeight: 700, color: '#f8fafc', marginBottom: '6px' }}>
          Paso 1 · Inspeccionar la estructura autorizada (Persistida en Backend)
        </div>
        {declaredUnits.length === 0 ? (
          <div
            role="status"
            style={{
              padding: '10px 12px',
              borderRadius: '8px',
              background: 'rgba(120, 53, 15, 0.28)',
              border: '1px solid rgba(245, 158, 11, 0.45)',
              color: '#fde68a',
            }}
          >
            <strong>Organización LIVE no constituida:</strong> El backend devuelve{' '}
            <code>0</code> unidades en <code>organization_units</code>,{' '}
            <code>{registeredProfilesCount}</code> perfiles en <code>organization_profiles</code> y{' '}
            <code>{historicalAgentCount}</code> principales históricos con credencial deshabilitada.
            No se inventan departamentos a partir de nombres de agente ni modelos LLM.
          </div>
        ) : (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
            {declaredUnits.map((u) => (
              <span
                key={u.id}
                style={{
                  padding: '4px 8px',
                  borderRadius: '6px',
                  background: 'rgba(30, 41, 59, 0.9)',
                  border: '1px solid rgba(56, 189, 248, 0.3)',
                  fontSize: '11px',
                }}
              >
                <strong>[{u.code}]</strong> {u.name} ({u.id}) · Padre: {u.parentId || 'Raíz'} · Resp: {u.leadRole}
              </span>
            ))}
          </div>
        )}
      </section>

      {/* Step 2: Prepare Proposed Structure (Local Draft) */}
      <section
        style={{
          padding: '12px 14px',
          borderRadius: '10px',
          background: 'rgba(15, 23, 42, 0.78)',
          border: '1px solid rgba(148, 163, 184, 0.2)',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
          <div style={{ fontWeight: 700, color: '#f8fafc' }}>
            Paso 2 · Preparar estructura propuesta (Borrador Local)
          </div>
          <span
            style={{
              padding: '2px 8px',
              borderRadius: '999px',
              fontSize: '10px',
              fontWeight: 700,
              background: 'rgba(56, 189, 248, 0.16)',
              color: '#7dd3fc',
              border: '1px solid rgba(56, 189, 248, 0.35)',
            }}
          >
            PROPUESTA LOCAL · NO PERSISTIDA ({draftUnits.length} unidad(es), {draftProfiles.length} perfil(es))
          </span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
          {/* Add Unit to Proposal */}
          <form
            onSubmit={handleStageUnitDraft}
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
              padding: '10px',
              borderRadius: '8px',
              background: 'rgba(2, 6, 23, 0.55)',
              border: '1px solid rgba(148, 163, 184, 0.18)',
            }}
          >
            <strong style={{ color: '#e2e8f0' }}>+ Añadir departamento a la propuesta</strong>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 90px', gap: '6px' }}>
              <input
                aria-label="ID de unidad propuesta"
                placeholder="unit-eng"
                value={unitId}
                onChange={(e) => setUnitId(e.target.value)}
                style={{ padding: '6px 8px', borderRadius: '6px', background: '#0f172a', color: '#f8fafc', border: '1px solid #334155', fontSize: '11px' }}
              />
              <input
                aria-label="Código de unidad propuesta"
                placeholder="ENG"
                value={unitCode}
                onChange={(e) => setUnitCode(e.target.value)}
                style={{ padding: '6px 8px', borderRadius: '6px', background: '#0f172a', color: '#f8fafc', border: '1px solid #334155', fontSize: '11px' }}
              />
            </div>
            <input
              aria-label="Nombre de unidad propuesta"
              placeholder="Ingeniería de Plataforma"
              value={unitName}
              onChange={(e) => setUnitName(e.target.value)}
              style={{ padding: '6px 8px', borderRadius: '6px', background: '#0f172a', color: '#f8fafc', border: '1px solid #334155', fontSize: '11px' }}
            />
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }}>
              <input
                aria-label="Rol responsable de unidad propuesta"
                placeholder="Lead Engineer"
                value={leadRole}
                onChange={(e) => setLeadRole(e.target.value)}
                style={{ padding: '6px 8px', borderRadius: '6px', background: '#0f172a', color: '#f8fafc', border: '1px solid #334155', fontSize: '11px' }}
              />
              <input
                aria-label="Unidad padre propuesta"
                placeholder="Padre (opcional, ej. unit-exec)"
                value={parentId}
                onChange={(e) => setParentId(e.target.value)}
                style={{ padding: '6px 8px', borderRadius: '6px', background: '#0f172a', color: '#f8fafc', border: '1px solid #334155', fontSize: '11px' }}
              />
            </div>
            <input
              aria-label="Principal responsable de unidad propuesta"
              placeholder="Principal responsable (opcional)"
              value={leadPrincipalId}
              onChange={(e) => setLeadPrincipalId(e.target.value)}
              style={{ padding: '6px 8px', borderRadius: '6px', background: '#0f172a', color: '#f8fafc', border: '1px solid #334155', fontSize: '11px' }}
            />
            <input
              aria-label="Descripción de unidad propuesta"
              placeholder="Responsabilidades y mandato del departamento"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              style={{ padding: '6px 8px', borderRadius: '6px', background: '#0f172a', color: '#f8fafc', border: '1px solid #334155', fontSize: '11px' }}
            />
            <button
              type="submit"
              className="aao-hud-btn"
              style={{ alignSelf: 'flex-start', padding: '5px 10px', fontSize: '11px', fontWeight: 700 }}
            >
              Añadir unidad al borrador
            </button>
          </form>

          {/* Add Profile Attribution to Proposal */}
          <form
            onSubmit={handleStageProfileDraft}
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
              padding: '10px',
              borderRadius: '8px',
              background: 'rgba(2, 6, 23, 0.55)',
              border: '1px solid rgba(148, 163, 184, 0.18)',
            }}
          >
            <strong style={{ color: '#e2e8f0' }}>+ Añadir adscripción de perfil a la propuesta</strong>
            <input
              aria-label="Principal ID del perfil propuesto"
              placeholder="Principal ID (ej. worker-1)"
              value={principalId}
              onChange={(e) => setPrincipalId(e.target.value)}
              list="constitution-known-principals"
              style={{ padding: '6px 8px', borderRadius: '6px', background: '#0f172a', color: '#f8fafc', border: '1px solid #334155', fontSize: '11px' }}
            />
            <datalist id="constitution-known-principals">
              {agents.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} ({a.unitId})
                </option>
              ))}
            </datalist>
            <select
              aria-label="Unidad destino del perfil propuesto"
              value={profileUnitId}
              onChange={(e) => setProfileUnitId(e.target.value)}
              style={{ padding: '6px 8px', borderRadius: '6px', background: '#0f172a', color: '#f8fafc', border: '1px solid #334155', fontSize: '11px' }}
            >
              <option value="">Selecciona unidad destino (persistida o en borrador)...</option>
              {availableUnitsForProfile.map((u) => (
                <option key={u.id} value={u.id}>
                  [{u.code}] {u.name} ({u.source === 'DRAFT' ? 'En borrador' : 'Persistida'})
                </option>
              ))}
            </select>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }}>
              <input
                aria-label="Puesto o rol del perfil propuesto"
                placeholder="Rol / puesto (ej. Backend Engineer)"
                value={roleTitle}
                onChange={(e) => setRoleTitle(e.target.value)}
                style={{ padding: '6px 8px', borderRadius: '6px', background: '#0f172a', color: '#f8fafc', border: '1px solid #334155', fontSize: '11px' }}
              />
              <input
                aria-label="Responsable jerárquico del perfil propuesto"
                placeholder="Manager principal (opcional)"
                value={managerPrincipalId}
                onChange={(e) => setManagerPrincipalId(e.target.value)}
                style={{ padding: '6px 8px', borderRadius: '6px', background: '#0f172a', color: '#f8fafc', border: '1px solid #334155', fontSize: '11px' }}
              />
            </div>
            <input
              aria-label="Competencias del perfil propuesto"
              placeholder="Competencias separadas por coma (ej. rust, postgres)"
              value={competenciesText}
              onChange={(e) => setCompetenciesText(e.target.value)}
              style={{ padding: '6px 8px', borderRadius: '6px', background: '#0f172a', color: '#f8fafc', border: '1px solid #334155', fontSize: '11px' }}
            />
            <button
              type="submit"
              className="aao-hud-btn"
              style={{ alignSelf: 'flex-start', padding: '5px 10px', fontSize: '11px', fontWeight: 700 }}
            >
              Añadir perfil al borrador
            </button>
          </form>
        </div>

        {/* Staged Proposal Items List */}
        {(draftUnits.length > 0 || draftProfiles.length > 0) && (
          <div
            data-testid="constitution-staged-proposal"
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '6px',
              padding: '10px',
              borderRadius: '8px',
              background: 'rgba(14, 116, 144, 0.14)',
              border: '1px dashed rgba(56, 189, 248, 0.45)',
            }}
          >
            <strong style={{ color: '#7dd3fc', fontSize: '11px' }}>
              Elementos en borrador local (aún no enviados al backend):
            </strong>
            {draftUnits.map((u) => (
              <div
                key={u.draftId}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '4px 8px',
                  borderRadius: '6px',
                  background: 'rgba(15, 23, 42, 0.85)',
                }}
              >
                <span>
                  🏛️ <strong>[{u.code}] {u.name}</strong> (<code>{u.id}</code>) · Rol: {u.leadRole}
                  {u.parent_id ? ` · Padre: ${u.parent_id}` : ''}
                </span>
                <button
                  type="button"
                  onClick={() => handleRemoveUnitDraft(u.draftId)}
                  className="aao-hud-btn"
                  style={{ padding: '2px 6px', fontSize: '10px' }}
                >
                  Quitar
                </button>
              </div>
            ))}
            {draftProfiles.map((p) => (
              <div
                key={p.draftId}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '4px 8px',
                  borderRadius: '6px',
                  background: 'rgba(15, 23, 42, 0.85)',
                }}
              >
                <span>
                  👤 <strong>{p.principal_id}</strong> → Unidad <code>{p.unit_id}</code> · Puesto: {p.role_title}
                  {p.manager_principal_id ? ` · Manager: ${p.manager_principal_id}` : ''}
                </span>
                <button
                  type="button"
                  onClick={() => handleRemoveProfileDraft(p.draftId)}
                  className="aao-hud-btn"
                  style={{ padding: '2px 6px', fontSize: '10px' }}
                >
                  Quitar
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Step 3: Validate Competencies & Governance Rules */}
      <section
        data-testid="constitution-step3-validation"
        style={{
          padding: '12px 14px',
          borderRadius: '10px',
          background: 'rgba(15, 23, 42, 0.78)',
          border: '1px solid rgba(148, 163, 184, 0.2)',
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
        }}
      >
        <div style={{ fontWeight: 700, color: '#f8fafc' }}>
          Paso 3 · Validar competencias, jerarquía y reglas constitucionales
        </div>
        <div
          style={{
            padding: '8px 10px',
            borderRadius: '6px',
            background: 'rgba(30, 41, 59, 0.75)',
            borderLeft: '3px solid #38bdf8',
            color: '#cbd5e1',
            fontSize: '11px',
          }}
        >
          ℹ️ {validation.constitutionalNotice}
        </div>

        {validation.errors.length > 0 && (
          <div
            role="alert"
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '4px',
              padding: '8px 10px',
              borderRadius: '6px',
              background: 'rgba(127, 29, 29, 0.35)',
              border: '1px solid rgba(248, 113, 113, 0.5)',
              color: '#fecaca',
            }}
          >
            {validation.errors.map((err, i) => (
              <div key={`${err.code}-${i}`}>⛔ {err.message}</div>
            ))}
          </div>
        )}

        {validation.warnings.map((w, i) => (
          <div
            key={`${w.code}-${i}`}
            style={{
              padding: '8px 10px',
              borderRadius: '6px',
              background: 'rgba(120, 53, 15, 0.25)',
              border: '1px solid rgba(245, 158, 11, 0.4)',
              color: '#fde68a',
            }}
          >
            ⚠️ {w.message}
          </div>
        ))}
      </section>

      {/* Step 4 & Step 5: Execute Authorized Operations & Refresh LIVE Office */}
      <section
        style={{
          padding: '12px 14px',
          borderRadius: '10px',
          background: 'rgba(15, 23, 42, 0.78)',
          border: '1px solid rgba(148, 163, 184, 0.2)',
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
        }}
      >
        <div style={{ fontWeight: 700, color: '#f8fafc' }}>
          Pasos 4 y 5 · Registrar mediante operaciones autorizadas y actualizar Oficina LIVE
        </div>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
          <button
            type="button"
            disabled={!validation.canSubmitAuthorized || isSubmitting}
            onClick={() => void handleExecuteAuthorizedConstitution()}
            data-testid="constitution-submit-btn"
            style={{
              padding: '7px 14px',
              borderRadius: '8px',
              fontWeight: 700,
              fontSize: '12px',
              cursor: validation.canSubmitAuthorized && !isSubmitting ? 'pointer' : 'not-allowed',
              background: validation.canSubmitAuthorized ? '#0284c7' : 'rgba(51, 65, 85, 0.6)',
              color: validation.canSubmitAuthorized ? '#f8fafc' : '#94a3b8',
              border: '1px solid rgba(56, 189, 248, 0.4)',
            }}
          >
            {isSubmitting
              ? 'Registrando en backend...'
              : '4. Registrar estructura en Backend (PUT /v1/organization/*)'}
          </button>

          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              className="aao-hud-btn"
              style={{ padding: '7px 12px', fontSize: '11px', fontWeight: 700 }}
            >
              5. ↻ Reconstruir Oficina desde GET /v1/organization
            </button>
          )}
        </div>

        {executionLogs.length > 0 && (
          <div
            role="status"
            data-testid="constitution-execution-logs"
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '4px',
              padding: '8px 10px',
              borderRadius: '8px',
              background: 'rgba(2, 6, 23, 0.75)',
              border: '1px solid rgba(148, 163, 184, 0.25)',
            }}
          >
            {executionLogs.map((log, index) => (
              <div
                key={index}
                style={{
                  color:
                    log.kind === 'error'
                      ? '#fca5a5'
                      : log.kind === 'success'
                      ? '#6ee7b7'
                      : '#7dd3fc',
                }}
              >
                {log.kind === 'error' ? '❌ ' : log.kind === 'success' ? '✅ ' : '🔄 '}
                {log.message}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
};
