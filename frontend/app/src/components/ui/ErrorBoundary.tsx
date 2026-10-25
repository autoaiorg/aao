import { Component, ErrorInfo, ReactNode } from 'react';
import { Card } from './Card';
import { Button } from './Button';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // In strict mode or production, do not log tokens or sensitive data
    console.error('ErrorBoundary capturó una excepción:', error.message, errorInfo.componentStack);
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div style={{ padding: '24px' }}>
          <Card
            elevation="none"
            style={{
              backgroundColor: 'var(--status-error-bg)',
              border: '1px solid var(--status-error-border)',
              padding: '24px',
            }}
          >
            <h3 style={{ color: 'var(--status-error-text)', marginBottom: '8px', fontSize: '16px' }}>
              Se produjo un error inesperado en la interfaz
            </h3>
            <p style={{ color: 'var(--status-error-text)', fontSize: '13px', marginBottom: '16px' }}>
              {this.state.error?.message || 'Error desconocido de renderizado'}
            </p>
            <Button variant="danger" size="sm" onClick={this.handleReset}>
              Restablecer componente
            </Button>
          </Card>
        </div>
      );
    }

    return this.props.children;
  }
}
