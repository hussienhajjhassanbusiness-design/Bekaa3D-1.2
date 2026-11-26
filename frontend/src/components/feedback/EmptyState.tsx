import Link from "next/link";
import { Button, buttonLinkClassName } from "@/components/forms/Button";
import { Icon, type IconName } from "@/components/ui/Icon";

export interface EmptyStateProps {
  message: string;
  actionLabel?: string;
  onAction?: () => void;
  // Navigation action (Batch 7): with `actionLabel`, renders the primary
  // action as a link instead of a button. Ignored when `onAction` is set.
  actionHref?: string;
  // Decorative glyph in the circle (Batch 5); defaults to the original one.
  icon?: IconName;
}

// Stitch empty state (COMPONENT-SPECS §49): a 96px lavender circle with a
// neutral (not brand-green) icon, a one-line explanation, and at most one
// primary action. `icon` (optional, presentation only) was added in Batch 5,
// `actionHref` in Batch 7.
export function EmptyState({ message, actionLabel, onAction, actionHref, icon = "search" }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-4 px-4 py-16 text-center">
      <div className="flex h-24 w-24 items-center justify-center rounded-full bg-surface-container">
        <Icon name={icon} className="h-12 w-12 text-outline" strokeWidth={1.5} />
      </div>
      <p className="max-w-sm text-body-md text-on-surface-variant">{message}</p>
      {actionLabel && onAction && (
        <Button type="button" onClick={onAction} className="mt-2">
          {actionLabel}
        </Button>
      )}
      {actionLabel && !onAction && actionHref && (
        <Link href={actionHref} className={`mt-2 ${buttonLinkClassName("primary")}`}>
          {actionLabel}
        </Link>
      )}
    </div>
  );
}
