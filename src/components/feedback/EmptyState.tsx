import { Button } from "@/components/forms/Button";

export interface EmptyStateProps {
  message: string;
  actionLabel?: string;
  onAction?: () => void;
}

// bekaa3d-brand-ui convention: centered neutral (not brand-colored) icon
// + one-line explanation + at most one primary action — never a
// decorative brand-green illustration filling the space.
export function EmptyState({ message, actionLabel, onAction }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-3 py-12 text-center">
      <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" className="h-10 w-10 text-neutral-400">
        <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.5" />
        <path d="M20 20l-3.2-3.2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
      <p className="text-body text-text-secondary">{message}</p>
      {actionLabel && onAction && (
        <Button type="button" onClick={onAction}>
          {actionLabel}
        </Button>
      )}
    </div>
  );
}
