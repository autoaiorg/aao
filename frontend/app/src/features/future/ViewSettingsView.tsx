import React from 'react';
import { Card } from '../../components/ui/Card';
import { SectionHeading } from '../../components/ui/SectionHeading';
import { Button } from '../../components/ui/Button';

export interface ViewSettingsViewProps {
  staleTimeSeconds: number;
  onStaleTimeChange: (seconds: number) => void;
  onClearCache: () => void;
}

export const ViewSettingsView: React.FC<ViewSettingsViewProps> = ({
  staleTimeSeconds,
  onStaleTimeChange,
  onClearCache,
}) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <SectionHeading
        title="Configuración de Vista y Rendimiento"
        subtitle="Ajustes de cliente, frescura de datos y accesibilidad"
      />

      <Card elevation="sm">
        <h3 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '12px' }}>
          Políticas de Caché y Frescura (TanStack Query)
        </h3>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '16px' }}>
          Para evitar sobrecargar los endpoints de auditoría y base de datos con peticiones repetitivas, el cliente utiliza una ventana de frescura conservadora.
        </p>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '20px' }}>
          <label htmlFor="stale-time-select" style={{ fontSize: '13px', fontWeight: 500 }}>
            Tiempo de frescura (staleTime):
          </label>
          <select
            id="stale-time-select"
            value={staleTimeSeconds}
            onChange={(e) => onStaleTimeChange(Number(e.target.value))}
            style={{
              padding: '6px 12px',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-strong)',
              backgroundColor: 'var(--bg-app)',
              fontSize: '13px',
            }}
          >
            <option value={15}>15 segundos (Recomendado)</option>
            <option value={30}>30 segundos</option>
            <option value={60}>60 segundos</option>
            <option value={0}>0 segundos (Revalidación inmediata)</option>
          </select>
        </div>

        <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '16px' }}>
          <Button variant="outline" size="sm" onClick={onClearCache}>
            Vaciar toda la caché de consultas en memoria
          </Button>
        </div>
      </Card>

      <Card elevation="sm">
        <h3 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '12px' }}>
          Verificación de Accesibilidad y Viewports
        </h3>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
          La interfaz ha sido diseñada conforme a WCAG 2.2 AA y probada en los viewports normativos:
        </p>
        <ul style={{ paddingLeft: '20px', fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          <li><strong>Móvil (390 px):</strong> Navegación en cajón accesible, métricas apiladas en una columna sin scroll horizontal.</li>
          <li><strong>Tablet (768 px):</strong> Menú lateral plegable, reflujo de tarjetas de cartera.</li>
          <li><strong>Escritorio (1440 px):</strong> Diseño completo de dos columnas con navegación fija.</li>
        </ul>
      </Card>
    </div>
  );
};
