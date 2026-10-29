type LoadingStateProps = {
  message?: string;
};

export function LoadingState({ message = "Loading" }: LoadingStateProps) {
  return (
    <div className="loading-state" role="status" aria-live="polite">
      <div className="loading-state__shell">
        <div className="loading-bar" aria-hidden="true">
          <span className="loading-bar__fill" />
        </div>
        <p className="loading-state__label">
          <span className="loading-state__spinner" aria-hidden="true" />
          <span>{message}</span>
        </p>
      </div>
    </div>
  );
}
