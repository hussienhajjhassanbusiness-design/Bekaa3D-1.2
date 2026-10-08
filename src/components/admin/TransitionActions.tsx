import { OrderActionButtons } from "@/components/feedback/OrderActionButtons";
import type { TransitionAffordance } from "@/lib/admin/adminOrderModel";

export interface TransitionActionsProps {
  actions: readonly TransitionAffordance[];
  pendingActionId?: string | null;
  onSelectAction: (actionId: string) => void;
}

// #SECURITY-SERVER-FULFILLMENT-STATE-MACHINE
//
// Thin wrapper over the shared OrderActionButtons primitive
// (FVS-031-IMPLEMENTATION-PLAN.md §1 extraction) — preserves this
// component's exact existing name/props/behavior for every current
// admin caller; see OrderActionButtons.tsx for the actual rendering
// logic and its documentation.
export function TransitionActions(props: TransitionActionsProps) {
  return <OrderActionButtons {...props} />;
}
