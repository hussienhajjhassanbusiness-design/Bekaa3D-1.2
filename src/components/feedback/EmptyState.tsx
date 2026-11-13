import { Button } from "@/components/forms/Button";
import { Icon } from "@/components/ui/Icon";

export interface EmptyStateProps {
  message: string;
  actionLabel?: string;
  onAction?: () => void;
}

// Stitch empty state (COMPONENT-SPECS §49): a 96px lavender circle with a
// neutral (not brand-green) icon, a one-line explanation, and at most one
// primary action. Props are unchanged.
export function EmptyState({ message, actionLabel, onAction }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-4 px-4 py-16 text-center">
      <div className="flex h-24 w-24 items-center justify-center rounded-full bg-surface-container">
        <Icon name="search" className="h-12 w-12 text-outline" strokeWidth={1.5} />
      </div>
      <p className="max-w-sm text-body-md text-on-surface-variant">{message}</p>
      {actionLabel && onAction && (
        <Button type="button" onClick={onAction} className="mt-2">
          {actionLabel}
        </Button>
      )}
    </div>
  );
}
