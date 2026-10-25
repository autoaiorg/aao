import React from 'react';
import { Card } from '../../components/ui/Card';
import { SectionHeading, PermissionNotice } from '../../components/ui/SectionHeading';
import { Badge } from '../../components/ui/Card';

export const OrganizationView: React.FC = () => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div>
        <SectionHeading
          title="Organización y Agentes (Fase F3 — En Planificación)"
          subtitle="Diseño arquitectónico para la estructura de agentes, unidades organizativas y asignaciones"
        />
        <PermissionNotice message="Esta capacidad está reservada para la fase F3 y no dispone de endpoints en el backend actual. No se simulan agentes activos ni órdenes ejecutivas sin contrato autenticado." />
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
          <Badge variant="info">Preparación de Fase F3</Badge>
        </div>
        <h3 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '8px' }}>
          Módulo no disponible en esta fase
        </h3>
        <p style={{ color: 'var(--text-secondary)', fontSize: '13px', maxWidth: '600px', margin: '0 auto 20px auto', lineHeight: 1.5 }}>
          La visualización de la estructura organizativa requiere contratos de backend para unidades de organización, identidades de agentes, asignación de tareas y disponibilidad. Conforme al principio de honestidad técnica, no se renderizan agentes simulados como si estuvieran operando.
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
            Modelos de dominio proyectados para F3:
          </strong>
          <ul style={{ paddingLeft: '20px', color: 'var(--text-secondary)' }}>
            <li><code>OrganizationUnit</code>: Unidades funcionales con directivas y proyectos asignados.</li>
            <li><code>AgentIdentity</code>: Identidades individuales con pares de claves y auditoría de turnos.</li>
            <li><code>Assignment</code>: Tareas asignadas formalmente por mandato o cola de trabajo.</li>
            <li><code>Authority</code>: Límites de delegación y facultades R0-R3 explícitas.</li>
          </ul>
        </div>
      </Card>
    </div>
  );
};
