import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { OriginBadge, FreshnessIndicator } from '../components/ui/OriginBadge';
import { BannerAlert } from '../components/layout/BannerAlert';
import { TopBar } from '../components/layout/TopBar';
import { StateDistribution } from '../components/ui/StateDistribution';
import { ErrorBoundary } from '../components/ui/ErrorBoundary';

describe('UI Presentation & Component Integrity', () => {
  it('OriginBadge renders appropriate indicator for LIVE and DEMO', () => {
    const { rerender } = render(<OriginBadge origin="live" />);
    expect(screen.getByText('LIVE · AUTORIZADO')).toBeInTheDocument();

    rerender(<OriginBadge origin="demo" />);
    expect(screen.getByText('DEMO · SIMULADO')).toBeInTheDocument();
  });

  it('BannerAlert shows persistent warning only in DEMO mode', () => {
    const { rerender } = render(<BannerAlert origin="live" />);
    expect(screen.queryByText(/DEMO · DATOS SIMULADOS/i)).toBeNull();

    rerender(<BannerAlert origin="demo" />);
    expect(screen.getByText(/DEMO · DATOS SIMULADOS · SIN CONEXIÓN AL NÚCLEO/i)).toBeInTheDocument();
  });

  it('FreshnessIndicator formats timestamp and triggers refresh callback', () => {
    const onRefresh = vi.fn();
    render(
      <FreshnessIndicator
        fetchedAt="2026-10-25T10:00:00Z"
        isFetching={false}
        onRefresh={onRefresh}
      />
    );

    expect(screen.getByText(/Actualizado:/i)).toBeInTheDocument();
    const btn = screen.getByRole('button', { name: /Actualizar datos/i });
    fireEvent.click(btn);
    expect(onRefresh).toHaveBeenCalled();
  });

  it('StateDistribution includes accessible progressbar and 6 stages', () => {
    const dist = {
      INBOX: 1,
      READY: 2,
      IN_PROGRESS: 3,
      IN_REVIEW: 1,
      VERIFIED: 2,
      DONE: 4,
    };
    render(<StateDistribution distribution={dist} totalCount={13} />);

    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '13');
    expect(screen.getByText('Entrada')).toBeInTheDocument();
    expect(screen.getByText('Preparado')).toBeInTheDocument();
    expect(screen.getByText('En curso')).toBeInTheDocument();
    expect(screen.getByText('Revisión')).toBeInTheDocument();
    expect(screen.getByText('Verificado')).toBeInTheDocument();
    expect(screen.getByText('Completado')).toBeInTheDocument();
  });

  it('TopBar allows toggling between LIVE and DEMO', () => {
    const onOriginChange = vi.fn();
    render(
      <TopBar
        origin="live"
        onOriginChange={onOriginChange}
        projects={[]}
        selectedProjectId={null}
        onProjectSelect={() => {}}
        principal={null}
        isAuthenticated={false}
        onLogin={() => {}}
        onLogout={() => {}}
        onRefresh={() => {}}
      />
    );

    const demoBtn = screen.getByRole('button', { name: 'DEMO' });
    fireEvent.click(demoBtn);
    expect(onOriginChange).toHaveBeenCalledWith('demo');
  });

  it('ErrorBoundary catches errors and displays recovery button without crashing', () => {
    const BadComponent = () => {
      throw new Error('Test boundary crash');
    };

    // Suppress expected console.error during boundary test
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <ErrorBoundary>
        <BadComponent />
      </ErrorBoundary>
    );

    expect(screen.getByText(/Se produjo un error inesperado/i)).toBeInTheDocument();
    expect(screen.getByText('Test boundary crash')).toBeInTheDocument();

    consoleSpy.mockRestore();
  });
});
