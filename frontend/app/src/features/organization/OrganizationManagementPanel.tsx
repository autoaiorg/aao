import React, { useState } from 'react';
import type { AgentIdentity, DataState, OrgUnit } from '../../domain/models';
import type {
  OrganizationProfileCommand,
  OrganizationUnitCommand,
} from '../../data/ports/AaoOrganizationCommandPort';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';

interface Props {
  units: OrgUnit[];
  agents: AgentIdentity[];
  onSaveUnit: (input: OrganizationUnitCommand) => Promise<DataState<unknown>>;
  onSaveProfile: (input: OrganizationProfileCommand) => Promise<DataState<unknown>>;
  onSaved: () => void;
}

export const OrganizationManagementPanel: React.FC<Props> = ({
  units,
  agents,
  onSaveUnit,
  onSaveProfile,
  onSaved,
}) => {
  const editableUnits = units.filter((unit) => unit.id !== 'unit-unassigned');
  const [unitId, setUnitId] = useState('');
  const [unitCode, setUnitCode] = useState('');
  const [unitName, setUnitName] = useState('');
  const [parentId, setParentId] = useState('');
  const [leadId, setLeadId] = useState('');
  const [principalId, setPrincipalId] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [roleTitle, setRoleTitle] = useState('');
  const [profileUnitId, setProfileUnitId] = useState('');
  const [managerId, setManagerId] = useState('');
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);

  const loadUnit = (id: string) => {
    setUnitId(id);
    const unit = editableUnits.find((item) => item.id === id);
    setUnitCode(unit?.code || '');
    setUnitName(unit?.name || '');
    setParentId(unit?.parentId || '');
    setLeadId(unit?.leadAgentId || '');
  };

  const runSave = async (save: () => Promise<DataState<unknown>>) => {
    setSaving(true);
    setMessage('');
    try {
      const result = await save();
      if (result.kind !== 'ready') {
        setMessage(result.kind === 'error' ? result.message : result.kind === 'forbidden' ? result.reason : 'No se pudo guardar el cambio.');
        return;
      }
      setMessage('Cambio guardado en PostgreSQL.');
      onSaved();
    } catch {
      setMessage('Error de red al guardar. No se ha confirmado ningún cambio.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card elevation="sm" style={{ display: 'grid', gap: 16 }}>
      <div>
        <h3 style={{ margin: 0 }}>Gestión organizativa</h3>
        <p style={{ margin: '6px 0 0', color: 'var(--text-secondary)', fontSize: 13 }}>
          Declara metadatos organizativos persistentes. No concede permisos ni cambia asignaciones.
        </p>
      </div>
      <form onSubmit={(event) => {
        event.preventDefault();
        void runSave(() => onSaveUnit({
          id: unitId.trim(), name: unitName.trim(), code: unitCode.trim(),
          parent_id: parentId || null, lead_principal_id: leadId || null, enabled: true,
        }));
      }} style={{ display: 'grid', gap: 8 }}>
        <h4 style={{ margin: 0 }}>Unidad</h4>
        <label>Unidad existente o ID nuevo
          <input required value={unitId} list="org-unit-ids" onChange={(event) => loadUnit(event.target.value)} />
          <datalist id="org-unit-ids">{editableUnits.map((unit) => <option key={unit.id} value={unit.id}>{unit.name}</option>)}</datalist>
        </label>
        <label>Nombre<input required maxLength={200} value={unitName} onChange={(event) => setUnitName(event.target.value)} /></label>
        <label>Código<input required maxLength={64} value={unitCode} onChange={(event) => setUnitCode(event.target.value)} /></label>
        <label>Unidad superior
          <select value={parentId} onChange={(event) => setParentId(event.target.value)}>
            <option value="">Sin unidad superior</option>
            {editableUnits.filter((unit) => unit.id !== unitId).map((unit) => <option key={unit.id} value={unit.id}>{unit.name}</option>)}
          </select>
        </label>
        <label>Responsable principal
          <select value={leadId} onChange={(event) => setLeadId(event.target.value)}>
            <option value="">Sin responsable declarado</option>
            {agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name} ({agent.id})</option>)}
          </select>
        </label>
        <Button type="submit" disabled={saving || !unitId.trim()}>Guardar unidad</Button>
      </form>
      <form onSubmit={(event) => {
        event.preventDefault();
        void runSave(() => onSaveProfile({
          principal_id: principalId.trim(), display_name: displayName.trim(), role_title: roleTitle.trim(),
          unit_id: profileUnitId || null, manager_principal_id: managerId || null, enabled: true,
        }));
      }} style={{ display: 'grid', gap: 8 }}>
        <h4 style={{ margin: 0 }}>Perfil de agente</h4>
        <label>Principal (ID registrado)
          <input required value={principalId} list="org-principal-ids" onChange={(event) => {
            setPrincipalId(event.target.value);
            const agent = agents.find((item) => item.id === event.target.value);
            if (agent) { setDisplayName(agent.name); setRoleTitle(agent.roleTitle); setProfileUnitId(agent.unitId === 'unit-unassigned' ? '' : agent.unitId); setManagerId(agent.managerId || ''); }
          }} />
          <datalist id="org-principal-ids">{agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</datalist>
        </label>
        <label>Nombre visible<input required maxLength={200} value={displayName} onChange={(event) => setDisplayName(event.target.value)} /></label>
        <label>Rol<input required maxLength={200} value={roleTitle} onChange={(event) => setRoleTitle(event.target.value)} /></label>
        <label>Unidad
          <select value={profileUnitId} onChange={(event) => setProfileUnitId(event.target.value)}>
            <option value="">Sin unidad declarada</option>
            {editableUnits.map((unit) => <option key={unit.id} value={unit.id}>{unit.name}</option>)}
          </select>
        </label>
        <label>Responsable
          <select value={managerId} onChange={(event) => setManagerId(event.target.value)}>
            <option value="">Sin responsable declarado</option>
            {agents.filter((agent) => agent.id !== principalId).map((agent) => <option key={agent.id} value={agent.id}>{agent.name} ({agent.id})</option>)}
          </select>
        </label>
        <Button type="submit" disabled={saving || !principalId.trim()}>Guardar perfil</Button>
      </form>
      {message && <p role="status" aria-live="polite">{message}</p>}
    </Card>
  );
};
