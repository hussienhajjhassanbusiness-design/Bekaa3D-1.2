import { useId } from "react";

export function LoadingSpinner() {
  const labelId = useId();

  return (
    <div role="status" aria-labelledby={labelId}>
      <svg
        aria-hidden="true"
        className="h-6 w-6 animate-spin motion-reduce:animate-none text-brand-dark-green"
        viewBox="0 0 24 24"
        fill="none"
      >
        <circle
          className="opacity-25"
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          strokeWidth="4"
        />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
        />
      </svg>
      <span id={labelId} className="sr-only">
        Loading…
      </span>
    </div>
  );
}
