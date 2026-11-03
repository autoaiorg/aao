import React, { useState, useMemo } from 'react';
import type {
  EnterpriseEntitySelection,
  EnterpriseProjection,
  OperationalTimelineEntry,
} from './enterpriseProjection';

export interface OperationalTimelinePanelProps {
  projection: EnterpriseProjection;
  fetchedAt?: string;
  onSelectEntity: (selection: EnterpriseEntitySelection) => void;
}

export const OperationalTimelinePanel: React.FC<OperationalTimelinePanelProps> = ({
  projection,
  fetchedAt,
  onSelectEntity,
}) => {
  const [categoryFilter, setCategoryFilter] = useState<'ALL' | OperationalTimelineEntry['category']>('ALL');

  const filteredEntries = useMemo(() => {
    if (categoryFilter === 'ALL') return projection.timelineEntries;
    return projection.timelineEntries.filter((e) => e.category === categoryFilter);
  }, [projection.timelineEntries, categoryFilter]);

  const totalRecordedCostUsd = useMemo(() => {
    return projection.timelineEntries.reduce(
      (sum, item) => sum + (typeof item.costEstimateUsd === 'number' ? item.costEstimateUsd : 0),
      0
    );
  }, [projection.timelineEntries]);

  return (
    <div
      data-testid="operational-timeline-panel"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        color: '#e2e8f0',
        fontSize: '12px',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
        <div>
          <strong style={{ fontSize: '14px', color: '#f8fafc', display: 'block' }}>
            ⏱️ Observabilidad y Cronología Operativa
          </strong>
          <span style={{ color: '#94a3b8', fontSize: '11px' }}>
            Historial cronológico de ejecuciones, asignaciones, alertas y decisiones con procedencia y frescura temporal.
          </span>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', fontSize: '11px' }}>
          <span
            style={{
              padding: '2px 8px',
              borderRadius: '999px',
              fontWeight: 700,
              background:
                projection.origin === 'demo'
                  ? 'rgba(245, 158, 11, 0.2)'
                  : 'rgba(16, 185, 129, 0.2)',
              color: projection.origin === 'demo' ? '#fcd34d' : '#6ee7b7',
              border: '1px solid currentColor',
            }}
          >
            Procedencia: {projection.origin.toUpperCase()}
          </span>
          {fetchedAt && (
            <span style={{ color: '#94a3b8' }}>
              Frescura: <code>{fetchedAt}</code>
            </span>
          )}
          {totalRecordedCostUsd > 0 && (
            <span style={{ color: '#7dd3fc', fontWeight: 700 }}>
              Coste registrado: ${totalRecordedCostUsd.toFixed(4)} USD
            </span>
          )}
        </div>
      </div>

      {/* Category Filter */}
      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
        {(['ALL', 'EXECUTION', 'ASSIGNMENT', 'DECISION', 'ALERT'] as const).map((cat) => (
          <button
            key={cat}
            type="button"
            onClick={() => setCategoryFilter(cat)}
            className="aao-hud-btn"
            style={{
              padding: '3px 9px',
              fontSize: '10px',
              fontWeight: 700,
              background: categoryFilter === cat ? '#0284c7' : undefined,
              color: categoryFilter === cat ? '#f8fafc' : undefined,
            }}
          >
            {cat === 'ALL'
              ? `Todos (${projection.timelineEntries.length})`
              : cat === 'EXECUTION'
              ? 'Ejecuciones'
              : cat === 'ASSIGNMENT'
              ? 'Asignaciones'
              : cat === 'DECISION'
              ? 'Decisiones'
              : 'Alertas'}
          </button>
        ))}
      </div>

      {filteredEntries.length === 0 ? (
        <div
          style={{
            padding: '12px',
            borderRadius: '8px',
            background: 'rgba(15, 23, 42, 0.8)',
            border: '1px solid rgba(148, 163, 184, 0.2)',
            color: '#94a3b8',
          }}
        >
          No hay eventos registrados para este filtro en la proyección actual.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {filteredEntries.map((entry) => (
            <div
              key={entry.id}
              data-testid={`timeline-entry-${entry.id}`}
              style={{
                padding: '8px 10px',
                borderRadius: '8px',
                background: 'rgba(15, 23, 42, 0.84)',
                border: entry.isBlocked
                  ? '1px solid rgba(248, 113, 113, 0.45)'
                  : '1px solid rgba(148, 163, 184, 0.2)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: '8px',
                flexWrap: 'wrap',
              }}
            >
              <div>
                <div style={{ display: 'flex', gap: '6px', alignItems: 'center', flexWrap: 'wrap' }}>
                  <span style={{ fontSize: '10px', color: '#38bdf8', fontWeight: 700 }}>
                    [{entry.category}]
                  </span>
                  <strong style={{ color: '#f8fafc', fontSize: '12px' }}>{entry.title}</strong>
                  <code style={{ fontSize: '10px', color: '#94a3b8' }}>{entry.timestamp}</code>
                </div>
                <div style={{ fontSize: '11px', color: '#cbd5e1', marginTop: '2px' }}>
                  {entry.detail}
                  {entry.modelLabel ? ` · Modelo observado: ${entry.modelLabel}` : ''}
                  {typeof entry.costEstimateUsd === 'number'
                    ? ` · Coste: $${entry.costEstimateUsd.toFixed(4)}`
                    : ''}
                </div>
              </div>

              <div style={{ display: 'flex', gap: '4px' }}>
                {entry.agentId && (
                  <button
                    type="button"
                    onClick={() => onSelectEntity({ kind: 'agent', id: entry.agentId! })}
                    className="aao-hud-btn"
                    style={{ padding: '2px 7px', fontSize: '10px' }}
                  >
                    Ver Agente
                  </button>
                )}
                {entry.projectId && (
                  <button
                    type="button"
                    onClick={() => onSelectEntity({ kind: 'project', id: entry.projectId! })}
                    className="aao-hud-btn"
                    style={{ padding: '2px 7px', fontSize: '10px' }}
                  >
                    Ver Proyecto
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
