export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-danger-border bg-danger-bg px-3 py-2.5" role="alert">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="mt-0.5 flex-none text-danger">
        <path d="M12 9v4M12 17h.01" />
        <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
      </svg>
      <div className="text-xs text-danger">
        {message}
        {onRetry && (
          <>
            {" "}
            <button type="button" onClick={onRetry} className="underline underline-offset-2">
              Try again
            </button>
          </>
        )}
      </div>
    </div>
  );
}
