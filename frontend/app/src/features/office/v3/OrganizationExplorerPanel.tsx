import React from 'react';
import type { AgentIdentity, AlertSummary, OrgUnit, ProjectSummary } from '../../../domain/models';
import type {
  EnterpriseEntitySelection,
  EnterpriseProjection,
  WorkstationPositionSlot,
} from './enterpriseProjection';

export interface OrganizationExplorerPanelProps {
  units: OrgUnit[];
  agents: AgentIdentity[];
  projects: ProjectSummary[];
  alerts: AlertSummary[];
  projection: EnterpriseProjection;
  selectedEntity: EnterpriseEntitySelection;
  onSelectEntity: (selection: EnterpriseEntitySelection) => void;
  onOpenConstitutionCenter: () => void;
}

const OCCUPANCY_BADGE: Record<
  WorkstationPositionSlot['occupancyState'],
  { label: string; color: string; bg: string }
> = {
  OCCUPIED_ACTIVE: {
    label: 'OCUPADO · EJECUTANDO',
    color: '#6ee7b7',
    bg: 'rgba(16, 185, 129, 0.18)',
  },
  OCCUPIED_IDLE: {
    label: 'OCUPADO · DISPONIBLE',
    color: '#7dd3fc',
    bg: 'rgba(56, 189, 248, 0.16)',
  },
  ASSIGNED_NO_LEASE: {
    label: 'ENCARGO SIN LEASE',
    color: '#fcd34d',
    bg: 'rgba(245, 158, 11, 0.18)',
  },
  VACANT: {
    label: 'PUESTO VACANTE',
    color: '#94a3b8',
    bg: 'rgba(148, 163, 184, 0.14)',
  },
};

export const OrganizationExplorerPanel: React.FC<OrganizationExplorerPanelProps> = ({
  units,
  agents,
  projects,
  alerts,
  projection,
  selectedEntity,
  onSelectEntity,
  onOpenConstitutionCenter,
}) => {
  return (
    <div
      data-testid="organization-explorer-panel"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '14px',
        color: '#e2e8f0',
        fontSize: '12px',
      }}
    >
      {/* 1. Central Atrium Enterprise Hub */}
      <div
        style={{
          padding: '10px 12px',
          borderRadius: '10px',
          background:
            selectedEntity.kind === 'atrium'
              ? 'rgba(14, 116, 144, 0.28)'
              : 'rgba(15, 23, 42, 0.85)',
          border:
            selectedEntity.kind === 'atrium'
              ? '1px solid #38bdf8'
              : '1px solid rgba(148, 163, 184, 0.25)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '10px',
          flexWrap: 'wrap',
        }}
      >
        <div>
          <strong style={{ color: '#f8fafc', fontSize: '13px', display: 'block' }}>
            🏛️ {projection.atrium.label}
          </strong>
          <span style={{ color: '#94a3b8', fontSize: '11px' }}>
            {projection.atrium.constitutionSummaryText}
          </span>
        </div>
        <div style={{ display: 'flex', gap: '6px' }}>
          <button
            type="button"
            onClick={() => onSelectEntity({ kind: 'atrium', id: 'atrium-central' })}
            className="aao-hud-btn"
            style={{ padding: '4px 10px', fontSize: '11px', fontWeight: 700 }}
          >
            Inspeccionar Atrio Central
          </button>
          <button
            type="button"
            onClick={onOpenConstitutionCenter}
            className="aao-hud-btn"
            style={{
              padding: '4px 10px',
              fontSize: '11px',
              fontWeight: 700,
              borderColor: 'rgba(56, 189, 248, 0.5)',
              color: '#7dd3fc',
            }}
          >
            ⚖️ Constitución Organizativa
          </button>
        </div>
      </div>

      {/* 2. Departments & Workstation Positions (Puestos) */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        <strong style={{ color: '#f8fafc', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.4px' }}>
          Departamentos y Puestos Organizativos ({units.length} unidad(es) · {projection.workstations.length} puesto(s))
        </strong>

        {units.map((unit) => {
          const unitWorkstations = projection.workstations.filter((w) => w.unitId === unit.id);
          const isUnitSelected =
            selectedEntity.kind === 'department' && selectedEntity.id === unit.id;

          return (
            <div
              key={unit.id}
              style={{
                padding: '10px 12px',
                borderRadius: '10px',
                background: isUnitSelected
                  ? 'rgba(30, 58, 138, 0.35)'
                  : 'rgba(15, 23, 42, 0.78)',
                border: isUnitSelected
                  ? '1px solid #60a5fa'
                  : '1px solid rgba(148, 163, 184, 0.2)',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                <div>
                  <button
                    type="button"
                    onClick={() => onSelectEntity({ kind: 'department', id: unit.id })}
                    style={{
                      background: 'none',
                      border: 'none',
                      padding: 0,
                      color: '#f8fafc',
                      fontWeight: 800,
                      fontSize: '13px',
                      cursor: 'pointer',
                      textAlign: 'left',
                    }}
                  >
                    [{unit.code}] {unit.name}
                  </button>
                  <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                    Responsable: <strong>{unit.leadRole}</strong>
                    {unit.parentId ? ` · Unidad superior: ${unit.parentId}` : ' · Unidad raíz'}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => onSelectEntity({ kind: 'department', id: unit.id })}
                  className="aao-hud-btn"
                  style={{ padding: '3px 8px', fontSize: '10px' }}
                >
                  Inspeccionar Departamento
                </button>
              </div>

              {/* Workstations Grid inside Department */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
                  gap: '6px',
                }}
              >
                {unitWorkstations.map((ws) => {
                  const badge = OCCUPANCY_BADGE[ws.occupancyState];
                  const isWsSelected =
                    selectedEntity.kind === 'workstation' && selectedEntity.id === ws.id;
                  return (
                    <div
                      key={ws.id}
                      data-testid={`workstation-card-${ws.id}`}
                      style={{
                        padding: '8px 10px',
                        borderRadius: '8px',
                        background: isWsSelected
                          ? 'rgba(14, 116, 144, 0.3)'
                          : 'rgba(2, 6, 23, 0.6)',
                        border: isWsSelected
                          ? '1px solid #38bdf8'
                          : '1px solid rgba(148, 163, 184, 0.18)',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '4px',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '4px' }}>
                        <strong style={{ fontSize: '11px', color: '#f8fafc' }}>
                          💺 Puesto #{ws.slotIndex} · {ws.positionTitle}
                        </strong>
                        <span
                          style={{
                            padding: '1px 6px',
                            borderRadius: '999px',
                            fontSize: '9px',
                            fontWeight: 800,
                            color: badge.color,
                            background: badge.bg,
                          }}
                        >
                          {badge.label}
                        </span>
                      </div>

                      <div style={{ fontSize: '10px', color: '#cbd5e1' }}>
                        Agente:{' '}
                        {ws.technicalIdentityId ? (
                          <button
                            type="button"
                            onClick={() =>
                              onSelectEntity({ kind: 'agent', id: ws.technicalIdentityId! })
                            }
                            style={{
                              background: 'none',
                              border: 'none',
                              padding: 0,
                              color: '#38bdf8',
                              fontWeight: 700,
                              cursor: 'pointer',
                              fontSize: '10px',
                            }}
                          >
                            {ws.assignedAgentName} ({ws.technicalIdentityId})
                          </button>
                        ) : (
                          <span style={{ color: '#94a3b8' }}>Sin ocupante asignado</span>
                        )}
                      </div>

                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '2px' }}>
                        <span style={{ fontSize: '10px', color: '#94a3b8' }}>
                          {ws.activeWorkId
                            ? `Encargo: ${ws.activeWorkId}`
                            : 'Sin encargo activo'}
                        </span>
                        <button
                          type="button"
                          onClick={() => onSelectEntity({ kind: 'workstation', id: ws.id })}
                          className="aao-hud-btn"
                          style={{ padding: '2px 7px', fontSize: '10px' }}
                        >
                          Ver Puesto
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      {/* 3. Meeting Tables & Verified Coordinations */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        <strong style={{ color: '#f8fafc', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.4px' }}>
          Mesas de Reunión y Coordinación ({projection.meetingTables.length})
        </strong>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '8px' }}>
          {projection.meetingTables.map((table) => (
            <div
              key={table.id}
              style={{
                padding: '8px 10px',
                borderRadius: '8px',
                background: 'rgba(15, 23, 42, 0.78)',
                border: '1px solid rgba(148, 163, 184, 0.2)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              <div>
                <strong style={{ color: '#f8fafc', fontSize: '11px', display: 'block' }}>
                  🤝 {table.label}
                </strong>
                <span style={{ fontSize: '10px', color: table.hasVerifiedMeeting ? '#6ee7b7' : '#94a3b8' }}>
                  {table.hasVerifiedMeeting
                    ? `${table.activeCoordinations.length} coordinación(es) activa(s) acreditada(s)`
                    : 'Sin reunión acreditada en curso'}
                </span>
              </div>
              <button
                type="button"
                onClick={() => onSelectEntity({ kind: 'meeting-table', id: table.id })}
                className="aao-hud-btn"
                style={{ padding: '3px 8px', fontSize: '10px' }}
              >
                Inspeccionar Mesa
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* 4. Projects & Alerts Quick Selectors */}
      {(projects.length > 0 || alerts.length > 0 || agents.length > 0) && (
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {projects.map((proj) => (
            <button
              key={proj.id}
              type="button"
              onClick={() => onSelectEntity({ kind: 'project', id: proj.id })}
              className="aao-hud-btn"
              style={{ padding: '3px 8px', fontSize: '10px' }}
            >
              📁 Proyecto: {proj.name}
            </button>
          ))}
          {alerts.map((al) => (
            <button
              key={al.id}
              type="button"
              onClick={() => onSelectEntity({ kind: 'alert', id: al.id })}
              className="aao-hud-btn"
              style={{ padding: '3px 8px', fontSize: '10px', color: '#fca5a5' }}
            >
              🚨 Alerta: {al.title}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
