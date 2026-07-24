import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertCircle } from 'lucide-react';

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  retryCount: number;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null, retryCount: 0 };
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("ErrorBoundary caught an error:", error, errorInfo);
  }



  resetErrorBoundary = () => {
    this.setState((prev) => ({ 
      hasError: false, 
      error: null,
      retryCount: prev.retryCount + 1
    }));
  };

  render() {
    if (this.state.hasError) {
      const maxRetriesReached = this.state.retryCount >= 3;

      return (
        <div 
          className="workspace-loading" 
          style={{ 
            flexDirection: 'column', 
            gap: 12,
            color: 'var(--ws-red)'
          }}
        >
          <AlertCircle size={32} style={{ marginBottom: 4, opacity: 0.8 }} />
          <div style={{ fontWeight: 500, fontSize: '15px' }}>
            Something went wrong in this view.
          </div>
          <div style={{ fontSize: '13px', opacity: 0.7, maxWidth: 450, textAlign: 'center', marginBottom: 8, lineHeight: 1.5 }}>
            {maxRetriesReached 
              ? "This view continues to encounter a critical error. Please switch to another workspace or reload the page to restore functionality."
              : "An unexpected problem occurred while rendering this workspace. Your data is safe, but this view cannot be displayed."}
          </div>
          {!maxRetriesReached ? (
            <button 
              className="ws-btn ws-btn--ghost" 
              style={{ 
                borderColor: 'var(--ws-red-soft)',
                color: 'var(--ws-red)'
              }}
              onClick={this.resetErrorBoundary}
            >
              Try Again
            </button>
          ) : (
            <button 
              className="ws-btn ws-btn--ghost" 
              style={{ 
                borderColor: 'var(--ws-border)',
                color: 'var(--ws-text)'
              }}
              onClick={() => window.location.reload()}
            >
              Reload Application
            </button>
          )}
        </div>
      );
    }

    return this.props.children;
  }
}
