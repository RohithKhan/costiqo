type ErrorStateProps = {
  message: string;
  detail?: string;
  actionLabel?: string;
  onAction?: () => void;
};

export function ErrorState({ message, detail, actionLabel, onAction }: ErrorStateProps) {
  return (
    <div className="error-state">
      <div className="error-state__body">
        <p className="error-state__title">{message}</p>
        {detail ? <p className="small-copy">{detail}</p> : null}
      </div>
      {actionLabel && onAction ? (
        <button type="button" className="secondary-button" onClick={onAction}>
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}
