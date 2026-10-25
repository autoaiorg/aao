import React from 'react';
import { Card } from '../../components/ui/Card';
import { SectionHeading, PermissionNotice } from '../../components/ui/SectionHeading';
import { Badge } from '../../components/ui/Card';

export const VirtualOfficeView: React.FC = () => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div>
        <SectionHeading
          title="Oficina Virtual 3D (Fase F4 — En Planificación)"
          subtitle="Entorno espacial inmersivo para la supervisión contextual de la organización"
        />
        <PermissionNotice message="Three.js y la infraestructura 3D pesada han sido excluidos deliberadamente de esta entrega F1-F2 para cumplir con los presupuestos de rendimiento, bundle y estabilidad." />
      </div>

      <Card
        elevation="none"
        style={{
          backgroundColor: 'var(--bg-muted)',
          border: '1px dashed var(--border-strong)',
          padding: '32px 24px',
          textAlign: 'center',
        }}
      >
        <div style={{ display: 'inline-flex', marginBottom: '12px' }}>
          <Badge variant="demo">Preparación de Fase F4</Badge>
        </div>
        <h3 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '8px' }}>
          Escena 3D no cargada en esta fase
        </h3>
        <p style={{ color: 'var(--text-secondary)', fontSize: '13px', maxWidth: '640px', margin: '0 auto 20px auto', lineHeight: 1.5 }}>
          Conforme a la especificación técnica de Antigravity (AAO-FE-ARCH-2026-10-25), el bundle de producción debe permanecer ligero (&lt; 250 KB gzip objetivo) y accesible sin requerir aceleración GPU. La oficina 3D se desarrollará como módulo diferido (lazy loaded) en F4.
        </p>

        <div
          style={{
            textAlign: 'left',
            maxWidth: '650px',
            margin: '0 auto',
            backgroundColor: 'var(--bg-surface)',
            padding: '16px 20px',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border-subtle)',
            fontSize: '13px',
          }}
        >
          <strong style={{ color: 'var(--text-primary)', display: 'block', marginBottom: '8px' }}>
            Principios del ADR 003 para Oficina Virtual:
          </strong>
          <ul style={{ paddingLeft: '20px', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            <li><strong>Importación diferida:</strong> Three.js solo se descargará al ingresar explícitamente a la vista 3D.</li>
            <li><strong>Alternativa 2D obligatoria:</strong> Todo dato observable en la oficina 3D estará disponible en tarjetas 2D accesibles.</li>
            <li><strong>Límites de animación:</strong> Respeto estricto a la directiva de accesibilidad <code>prefers-reduced-motion</code>.</li>
            <li><strong>Veracidad operativa:</strong> Los avatares espaciales solo mostrarán presencia activa cuando exista heartbeat verificado.</li>
          </ul>
        </div>
      </Card>
    </div>
  );
};
