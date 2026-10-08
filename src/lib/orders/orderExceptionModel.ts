import type { OrderLineModel } from "./orderModel";
import type { OrderActionAffordance } from "./orderActionModel";

// #ARCHITECTURE-ORDER-EXCEPTION-ACTIONS
//
// Extends FVS-029's OrderLineModel via composition — never a forked
// copy. `customerCancelAction` is the one addition: the resolved,
// post-suppression action (see resolveCustomerCancelAction below),
// never a raw unfiltered server value.
export interface CancellableOrderLineModel extends OrderLineModel {
  customerCancelAction: OrderActionAffordance | null;
}

// #SECURITY-SERVER-CANCELLATION-AUTHORITY
//
// Defense-in-depth UX suppression only — the server capability
// remains the final authority regardless of what this function
// returns. It can only ever turn a supplied action into null for an
// STL line; it never fabricates an action the server did not supply,
// and a bug here can only make cancellation unavailable in the UI,
// never grant it.
export function resolveCustomerCancelAction(
  line: Pick<OrderLineModel, "productType">,
  serverAction: OrderActionAffordance | null
): OrderActionAffordance | null {
  if (line.productType === "stl") {
    return null;
  }
  return serverAction;
}
