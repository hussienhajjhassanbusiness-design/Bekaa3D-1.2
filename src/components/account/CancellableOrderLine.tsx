import { OrderLineItem } from "./OrderLineItem";
import { CancelOrderLineButton } from "./CancelOrderLineButton";
import type { CancellableOrderLineModel } from "@/lib/orders/orderExceptionModel";

export interface CancellableOrderLineProps {
  line: CancellableOrderLineModel;
  pendingActionId?: string | null;
  errorMessage?: string;
  onCancel: (lineId: string, actionId: string) => void;
}

// #ARCHITECTURE-CUSTOMER-ADMIN-ORDER-BOUNDARY
//
// Composes FVS-029's OrderLineItem completely unmodified alongside
// CancelOrderLineButton rendered separately — mirrors AdminOrderLine's
// exact composition structure. Each instance operates purely on its
// own `line` prop; no shared state exists between sibling lines.
export function CancellableOrderLine({ line, pendingActionId, errorMessage, onCancel }: CancellableOrderLineProps) {
  return (
    <div className="flex flex-col gap-2 tablet:flex-row tablet:items-center tablet:justify-between">
      <OrderLineItem line={line} />
      <CancelOrderLineButton
        action={line.customerCancelAction}
        pendingActionId={pendingActionId}
        errorMessage={errorMessage}
        onCancel={(actionId) => onCancel(line.id, actionId)}
      />
    </div>
  );
}
