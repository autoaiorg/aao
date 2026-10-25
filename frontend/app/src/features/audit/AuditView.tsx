import React from 'react';
import { Card } from '../../components/ui/Card';
import { SectionHeading, PermissionNotice } from '../../components/ui/SectionHeading';
import { Badge } from '../../components/ui/Card';

export const AuditView: React.FC = () => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div>
        <SectionHeading
          title="Auditoría y Certificación de Gobernanza"
          subtitle="Marco de aseguramiento independiente y trazabilidad de evidencia"
        />
        <PermissionNotice message="El estado de auditoría solo se considera certificado si existe dictamen independiente formal. Las pruebas automatizadas y los checks de CI no constituyen prueba de auditoría independiente." />
      </div>

      <Card elevation="sm">
        <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '8px' }}>
          Estado Actual de la Organización
        </h3>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
          Conforme a las políticas de AAO (GOV-REV-001 y AUTONOMOUS_GOVERNANCE_POLICY.md),
          las decisiones irreversibles y estratégicas están reservadas al CEO. Los niveles de
          gobernanza se estructuran en dos escalas ortogonales:
        </p>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: '16px',
            marginTop: '16px',
          }}
        >
          <div
            style={{
              padding: '12px',
              backgroundColor: 'var(--bg-muted)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
              <Badge variant="warning">Clasificación de Riesgo</Badge>
              <strong>R0 a R3</strong>
            </div>
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              R0 (Mínimo / Aislado), R1 (Operación local controlada), R2 (Efectos externos / mutaciones), R3 (Crítico / Gobernanza fundamental).
            </p>
          </div>

          <div
            style={{
              padding: '12px',
              backgroundColor: 'var(--bg-muted)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
              <Badge variant="info">Nivel de Garantía</Badge>
              <strong>Nivel A a D</strong>
            </div>
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              Nivel A (Sin auditoría formal), Nivel B (Pruebas reproducibles), Nivel C (Revisión técnica independiente), Nivel D (Certificación formal integral).
            </p>
          </div>
        </div>
      </Card>

      <Card elevation="sm">
        <h3 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '10px' }}>
          Matriz de Evidencias y Trazabilidad
        </h3>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
          Para consultar la evidencia exacta de verificación, consulte los registros canónicos del repositorio:
        </p>
        <ul style={{ paddingLeft: '20px', fontSize: '13px', color: 'var(--text-secondary)' }}>
          <li style={{ marginBottom: '6px' }}>
            <code>docs/COMPLIANCE_MATRIX.md</code>: Matriz de cumplimiento normativo y control de acceso.
          </li>
          <li style={{ marginBottom: '6px' }}>
            <code>docs/VERIFICATION_EVIDENCE_REGISTER.md</code>: Registro de SHAs y pruebas de verificación local.
          </li>
          <li style={{ marginBottom: '6px' }}>
            <code>docs/TECHNICAL_AUDIT.md</code>: Auditoría técnica y análisis de riesgos del núcleo.
          </li>
        </ul>
      </Card>
    </div>
  );
};
