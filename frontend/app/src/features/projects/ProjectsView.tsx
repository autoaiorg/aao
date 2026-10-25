import React, { useState } from 'react';
import type { ProjectSummary } from '../../domain/models';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { SectionHeading } from '../../components/ui/SectionHeading';

export interface ProjectsViewProps {
  projects: ProjectSummary[];
  selectedProjectId: string | null;
  onSelectProject: (id: string) => void;
  onViewDetails: (id: string) => void;
}

export const ProjectsView: React.FC<ProjectsViewProps> = ({
  projects,
  selectedProjectId,
  onSelectProject,
  onViewDetails,
}) => {
  const [search, setSearch] = useState('');

  const filtered = projects.filter(
    (p) =>
      p.name.toLowerCase().includes(search.toLowerCase()) ||
      (p.description && p.description.toLowerCase().includes(search.toLowerCase())) ||
      p.id.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <SectionHeading
        title="Cartera de Proyectos"
        subtitle="Listado de proyectos gobernados y autorizados para consulta en AAO"
      />

      <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
        <input
          type="search"
          placeholder="Buscar por nombre, ID o descripción..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Buscar proyectos"
          style={{
            padding: '8px 14px',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border-strong)',
            backgroundColor: 'var(--bg-surface)',
            color: 'var(--text-primary)',
            fontSize: '13px',
            width: '100%',
            maxWidth: '400px',
          }}
        />
      </div>

      {filtered.length === 0 ? (
        <Card elevation="none" style={{ textAlign: 'center', padding: '40px 20px' }}>
          <p style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>
            No se encontraron proyectos coincidentes.
          </p>
        </Card>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: '16px',
          }}
        >
          {filtered.map((proj) => {
            const isSelected = selectedProjectId === proj.id;
            return (
              <Card
                key={proj.id}
                elevation="sm"
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  border: isSelected ? '1px solid var(--border-focus)' : undefined,
                  gap: '16px',
                }}
              >
                <div>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'flex-start',
                      marginBottom: '8px',
                    }}
                  >
                    <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)' }}>
                      {proj.name}
                    </h3>
                    <span
                      style={{
                        fontSize: '11px',
                        padding: '2px 8px',
                        borderRadius: 'var(--radius-full)',
                        backgroundColor: 'var(--bg-muted)',
                        fontWeight: 600,
                        border: '1px solid var(--border-subtle)',
                      }}
                    >
                      {proj.status || 'ACTIVO'}
                    </span>
                  </div>

                  <div
                    style={{
                      fontSize: '11px',
                      fontFamily: 'monospace',
                      color: 'var(--text-muted)',
                      marginBottom: '8px',
                    }}
                  >
                    ID: {proj.id}
                  </div>

                  <p
                    style={{
                      fontSize: '13px',
                      color: 'var(--text-secondary)',
                      lineHeight: 1.4,
                    }}
                  >
                    {proj.description || 'Sin descripción provista por el contrato del proyecto.'}
                  </p>
                </div>

                <div
                  style={{
                    display: 'flex',
                    gap: '8px',
                    borderTop: '1px solid var(--border-subtle)',
                    paddingTop: '12px',
                  }}
                >
                  <Button
                    size="sm"
                    variant={isSelected ? 'secondary' : 'outline'}
                    onClick={() => onSelectProject(proj.id)}
                  >
                    {isSelected ? '✓ Seleccionado' : 'Seleccionar'}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => onViewDetails(proj.id)}
                  >
                    Ver Detalles →
                  </Button>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
};
