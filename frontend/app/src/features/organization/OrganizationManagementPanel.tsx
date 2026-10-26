import React, { useState } from 'react';
import type { AgentIdentity, DataState, OrgUnit } from '../../domain/models';
import type {
  OrganizationProfileCommand,
  OrganizationUnitCommand,
} from '../../data/ports/AaoOrganizationCommandPort';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import './organization-management.css';

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
  const [competencies, setCompetencies] = useState('');
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
    <Card elevation="sm" className="organization-management">
      <div className="organization-management__heading">
        <h3>Gestión organizativa</h3>
        <p>
          Declara metadatos organizativos persistentes. No concede permisos ni cambia asignaciones.
        </p>
      </div>
      <div className="organization-management__forms">
        <form className="organization-management__form" onSubmit={(event) => {
          event.preventDefault();
          void runSave(() => onSaveUnit({
            id: unitId.trim(), name: unitName.trim(), code: unitCode.trim(),
            parent_id: parentId || null, lead_principal_id: leadId || null, enabled: true,
          }));
        }}>
          <h4>Unidad</h4>
          <label className="organization-management__field organization-management__field--wide">Unidad existente o ID nuevo
            <input className="organization-management__control" required value={unitId} list="org-unit-ids" onChange={(event) => loadUnit(event.target.value)} />
            <datalist id="org-unit-ids">{editableUnits.map((unit) => <option key={unit.id} value={unit.id}>{unit.name}</option>)}</datalist>
          </label>
          <label className="organization-management__field">Nombre<input className="organization-management__control" required maxLength={200} value={unitName} onChange={(event) => setUnitName(event.target.value)} /></label>
          <label className="organization-management__field">Código<input className="organization-management__control" required maxLength={64} value={unitCode} onChange={(event) => setUnitCode(event.target.value)} /></label>
          <label className="organization-management__field">Unidad superior
            <select className="organization-management__control" value={parentId} onChange={(event) => setParentId(event.target.value)}>
              <option value="">Sin unidad superior</option>
              {editableUnits.filter((unit) => unit.id !== unitId).map((unit) => <option key={unit.id} value={unit.id}>{unit.name}</option>)}
            </select>
          </label>
          <label className="organization-management__field">Responsable principal
            <select className="organization-management__control" value={leadId} onChange={(event) => setLeadId(event.target.value)}>
              <option value="">Sin responsable declarado</option>
              {agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name} ({agent.id})</option>)}
            </select>
          </label>
          <div className="organization-management__submit"><Button type="submit" disabled={saving || !unitId.trim()}>Guardar unidad</Button></div>
        </form>
        <form className="organization-management__form" onSubmit={(event) => {
          event.preventDefault();
          void runSave(() => onSaveProfile({
            principal_id: principalId.trim(), display_name: displayName.trim(), role_title: roleTitle.trim(),
            unit_id: profileUnitId || null, manager_principal_id: managerId || null,
            competencies: competencies.split(',').map((value) => value.trim()).filter(Boolean), enabled: true,
          }));
        }}>
          <h4>Perfil de agente</h4>
          <label className="organization-management__field organization-management__field--wide">Principal (ID registrado)
            <input className="organization-management__control" required value={principalId} list="org-principal-ids" onChange={(event) => {
            setPrincipalId(event.target.value);
            const agent = agents.find((item) => item.id === event.target.value);
            if (agent) { setDisplayName(agent.name); setRoleTitle(agent.roleTitle); setProfileUnitId(agent.unitId === 'unit-unassigned' ? '' : agent.unitId); setManagerId(agent.managerId || ''); setCompetencies(agent.competencies?.join(', ') || ''); }
          }} />
            <datalist id="org-principal-ids">{agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</datalist>
          </label>
          <label className="organization-management__field">Nombre visible<input className="organization-management__control" required maxLength={200} value={displayName} onChange={(event) => setDisplayName(event.target.value)} /></label>
          <label className="organization-management__field">Rol<input className="organization-management__control" required maxLength={200} value={roleTitle} onChange={(event) => setRoleTitle(event.target.value)} /></label>
          <label className="organization-management__field">Unidad
            <select className="organization-management__control" value={profileUnitId} onChange={(event) => setProfileUnitId(event.target.value)}>
              <option value="">Sin unidad declarada</option>
              {editableUnits.map((unit) => <option key={unit.id} value={unit.id}>{unit.name}</option>)}
            </select>
          </label>
          <label className="organization-management__field">Responsable
            <select className="organization-management__control" value={managerId} onChange={(event) => setManagerId(event.target.value)}>
              <option value="">Sin responsable declarado</option>
              {agents.filter((agent) => agent.id !== principalId).map((agent) => <option key={agent.id} value={agent.id}>{agent.name} ({agent.id})</option>)}
            </select>
          </label>
          <label className="organization-management__field organization-management__field--wide">Competencias declaradas (separadas por comas)
            <input className="organization-management__control" maxLength={7000} value={competencies} onChange={(event) => setCompetencies(event.target.value)} aria-describedby="org-competencies-help" />
            <small id="org-competencies-help">Metadatos declarados por CEO; informan sugerencias de asignación y no acreditan competencia ni conceden permisos.</small>
          </label>
          <div className="organization-management__submit"><Button type="submit" disabled={saving || !principalId.trim()}>Guardar perfil</Button></div>
        </form>
      </div>
      {message && <p className="organization-management__message" role="status" aria-live="polite">{message}</p>}
    </Card>
  );
};
