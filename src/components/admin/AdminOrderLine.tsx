import { OrderLineItem } from "@/components/account/OrderLineItem";
import { TransitionActions } from "./TransitionActions";
import type { AdminOrderLineModel } from "@/lib/admin/adminOrderModel";

export interface AdminOrderLineProps {
  line: AdminOrderLineModel;
  pendingActionId?: string | null;
  onSelectAction: (lineId: string, actionId: string) => void;
}

// #ARCHITECTURE-CUSTOMER-ADMIN-ORDER-BOUNDARY
//
// Composes FVS-029's OrderLineItem completely unmodified (rendering
// `line` directly, since AdminOrderLineModel is a superset) alongside
// TransitionActions rendered separately — never injecting admin state
// into OrderLineItem itself. A digital/STL line's absence of
// transition controls comes naturally from an empty
// `availableActions` array, never a hardcoded product-type check.
export function AdminOrderLine({ line, pendingActionId, onSelectAction }: AdminOrderLineProps) {
  return (
    <div className="flex flex-col gap-2 tablet:flex-row tablet:items-center tablet:justify-between">
      <OrderLineItem line={line} />
      <TransitionActions
        actions={line.availableActions}
        pendingActionId={pendingActionId}
        onSelectAction={(actionId) => onSelectAction(line.id, actionId)}
      />
    </div>
  );
}
