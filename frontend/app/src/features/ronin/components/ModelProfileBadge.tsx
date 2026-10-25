import React from 'react';
import type { ModelProfile } from '../modelProfile';

export interface ModelProfileBadgeProps {
  profile: ModelProfile | null | undefined;
  compact?: boolean;
}

export const ModelProfileBadge: React.FC<ModelProfileBadgeProps> = ({ profile, compact = false }) => {
  if (!profile) {
    return (
      <span
        style={{
          fontSize: '11px',
          color: 'var(--text-muted)',
          fontStyle: 'italic',
        }}
      >
        Sin perfil de modelo declarado (selección por entorno)
      </span>
    );
  }

  const modelLabel = profile.model ?? 'modelo por defecto del CLI';

  if (compact) {
    return (
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
          padding: '2px 8px',
          borderRadius: 'var(--radius-sm, 4px)',
          backgroundColor: 'var(--bg-muted)',
          border: '1px solid var(--border-subtle)',
          fontSize: '11px',
        }}
      >
        <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
          🤖 {profile.provider}/{modelLabel}
        </span>
        <span style={{ color: 'var(--text-muted)', fontSize: '10px' }}>({profile.backend})</span>
        {profile.cost_per_attempt_usd !== null && profile.cost_per_attempt_usd !== undefined && (
          <span style={{ color: 'var(--accent)', fontWeight: 600, fontSize: '10px' }}>
            ~${profile.cost_per_attempt_usd.toFixed(2)}
          </span>
        )}
      </span>
    );
  }

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        padding: '10px 12px',
        borderRadius: 'var(--radius-md, 6px)',
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        fontSize: '11px',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <strong style={{ fontSize: '12px', color: 'var(--text-primary)' }}>
            🤖 Perfil de Modelo (Declarado en Catálogo)
          </strong>
        </div>
        <span
          style={{
            fontSize: '9px',
            padding: '1px 6px',
            borderRadius: '3px',
            backgroundColor: 'var(--status-info-bg)',
            color: 'var(--status-info-text)',
            border: '1px solid var(--status-info-border)',
            fontWeight: 700,
          }}
        >
          DECLARATIVO
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '8px' }}>
        <div>
          <span style={{ color: 'var(--text-muted)', fontSize: '10px', display: 'block' }}>Proveedor / Modelo</span>
          <strong style={{ color: 'var(--text-primary)' }}>
            {profile.provider} / {modelLabel}
          </strong>
        </div>

        <div>
          <span style={{ color: 'var(--text-muted)', fontSize: '10px', display: 'block' }}>Backend Ejecutor</span>
          <span style={{ fontFamily: 'monospace', color: 'var(--text-primary)' }}>{profile.backend}</span>
        </div>

        <div>
          <span style={{ color: 'var(--text-muted)', fontSize: '10px', display: 'block' }}>Coste Estimado / Intento</span>
          {profile.cost_per_attempt_usd !== null && profile.cost_per_attempt_usd !== undefined ? (
            <strong
              style={{
                color:
                  profile.cost_per_attempt_usd > 0 ? 'var(--accent)' : 'var(--status-success-text)',
              }}
            >
              ${profile.cost_per_attempt_usd.toFixed(2)} USD
              {profile.cost_per_attempt_usd === 0 && (
                <span style={{ fontSize: '10px', marginLeft: '4px', fontWeight: 500 }}>
                  (Declarado gratuito)
                </span>
              )}
            </strong>
          ) : (
            <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
              No declarado (desconocido)
            </span>
          )}
        </div>
      </div>

      {profile.seats && profile.seats.length > 0 ? (
        <div>
          <span style={{ color: 'var(--text-muted)', fontSize: '10px', display: 'block', marginBottom: '4px' }}>
            Seats Ofertados & Calidad Declarada (0–5):
          </span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
            {profile.seats.map((seat) => {
              const q = profile.quality ? profile.quality[seat] : undefined;
              return (
                <span
                  key={seat}
                  style={{
                    padding: '2px 6px',
                    borderRadius: 'var(--radius-sm, 4px)',
                    backgroundColor: 'var(--bg-muted)',
                    border: '1px solid var(--border-subtle)',
                    fontSize: '10px',
                    fontFamily: 'monospace',
                  }}
                >
                  {seat}
                  {typeof q === 'number' && (
                    <strong style={{ marginLeft: '4px', color: 'var(--accent)' }}>★{q}/5</strong>
                  )}
                </span>
              );
            })}
          </div>
        </div>
      ) : (
        <div>
          <span style={{ color: 'var(--text-muted)', fontSize: '10px', display: 'block', marginBottom: '4px' }}>
            Seats Ofertados:
          </span>
          <span style={{ color: 'var(--text-muted)', fontStyle: 'italic', fontSize: '10px' }}>
            Sin seats específicos declarados en el catálogo
          </span>
        </div>
      )}

      <div style={{ fontSize: '10px', color: 'var(--text-muted)', fontStyle: 'italic', marginTop: '2px' }}>
        * Valores declarados por el registro de la capacidad; la activación del proveedor y la comprobación de presupuesto
        se validan independientemente en el momento de la ejecución.
      </div>
    </div>
  );
};
