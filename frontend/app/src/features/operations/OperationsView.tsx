import React, { useState, useEffect } from 'react';
import { Card } from '../../components/ui/Card';
import { SectionHeading, PermissionNotice } from '../../components/ui/SectionHeading';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Card';

export interface OperationsViewProps {
  onRefreshAll: () => void;
}

export const OperationsView: React.FC<OperationsViewProps> = ({ onRefreshAll }) => {
  const [healthStatus, setHealthStatus] = useState<string>('Comprobando...');
  const [readyStatus, setReadyStatus] = useState<string>('Comprobando...');
  const [latencyMs, setLatencyMs] = useState<number | null>(null);

  const checkHealth = async () => {
    const start = performance.now();
    try {
      const res = await fetch('/health');
      const duration = Math.round(performance.now() - start);
      setLatencyMs(duration);
      if (res.ok) {
        setHealthStatus(`OK (${res.status})`);
      } else {
        setHealthStatus(`HTTP ${res.status}`);
      }
    } catch (err) {
      setHealthStatus('No disponible / Error de red');
    }

    try {
      const readyRes = await fetch('/ready');
      if (readyRes.ok) {
        setReadyStatus(`OK (${readyRes.status})`);
      } else {
        setReadyStatus(`HTTP ${readyRes.status}`);
      }
    } catch {
      setReadyStatus('No disponible');
    }
  };

  useEffect(() => {
    checkHealth();
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div>
        <SectionHeading
          title="Operaciones y Salud del Servicio"
          subtitle="Monitoreo de conectividad con la API FastAPI y endpoints de estado"
          action={
            <Button size="sm" variant="outline" onClick={() => { checkHealth(); onRefreshAll(); }}>
              ↻ Comprobar ahora
            </Button>
          }
        />
        <PermissionNotice message="La salud reportada refleja exclusivamente la accesibilidad de endpoints públicos de diagnóstico (/health, /ready)." />
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: '16px',
        }}
      >
        <Card elevation="sm">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Endpoint /health</span>
            <Badge variant={healthStatus.startsWith('OK') ? 'success' : 'warning'}>
              {healthStatus}
            </Badge>
          </div>
          <div style={{ fontSize: '20px', fontWeight: 700, marginTop: '8px' }}>
            Servicio FastAPI
          </div>
          <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
            {latencyMs !== null ? `Latencia estimada: ${latencyMs} ms` : 'Midiendo...'}
          </p>
        </Card>

        <Card elevation="sm">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Endpoint /ready</span>
            <Badge variant={readyStatus.startsWith('OK') ? 'success' : 'warning'}>
              {readyStatus}
            </Badge>
          </div>
          <div style={{ fontSize: '20px', fontWeight: 700, marginTop: '8px' }}>
            Preparación de Base de Datos
          </div>
          <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
            Estado de inicialización del pool PostgreSQL
          </p>
        </Card>
      </div>
    </div>
  );
};
