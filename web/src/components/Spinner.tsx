export function Spinner({ className = "" }: { className?: string }) {
  return (
    <svg
      className={`animate-spin ${className}`}
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      role="status"
      aria-label="Loading"
    >
      <path d="M21 12a9 9 0 1 1-3-6.7" />
    </svg>
  );
}
