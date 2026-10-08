import { OrderActionButtons } from "@/components/feedback/OrderActionButtons";
import type { OrderActionAffordance } from "@/lib/orders/orderActionModel";

export interface CancelOrderLineButtonProps {
  action: OrderActionAffordance | null;
  pendingActionId?: string | null;
  // Race-lost/generic-failure feedback only — caller-supplied,
  // pre-sanitized text (same established pattern as
  // InternalNoteEditor/ManualConfirmDialog's errorMessage prop).
  // Never raw backend error text
  // (#SECURITY-CANCELLATION-RACE-SERVER-WINS): this component never
  // interprets an error itself, and never retries automatically.
  errorMessage?: string;
  onCancel: (actionId: string) => void;
}

// #SECURITY-SERVER-CANCELLATION-AUTHORITY
//
// Composes the shared OrderActionButtons primitive with a single
// caller-supplied action — the identical server-provided-affordance
// architecture FVS-030 established, reused rather than duplicated.
// Absent when `action` is null (never a permanently disabled
// button); confirmation/pending/no-fetch behavior all come from
// OrderActionButtons itself.
export function CancelOrderLineButton({ action, pendingActionId, errorMessage, onCancel }: CancelOrderLineButtonProps) {
  return (
    <div>
      <OrderActionButtons
        actions={action ? [action] : []}
        pendingActionId={pendingActionId}
        onSelectAction={onCancel}
      />
      {errorMessage && (
        <p role="alert" className="mt-1 text-caption text-danger">
          {errorMessage}
        </p>
      )}
    </div>
  );
}
