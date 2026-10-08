import type { ReactNode } from "react";

export interface PaymentSuccessStateProps {
  orderDisplayId?: string;
  // Only ever renders a future next-step action (order history/
  // library) when the caller actually has a valid destination — no
  // dead link to FVS-029/FVS-020's still-unmounted routes.
  actionSlot?: ReactNode;
}

// #FVS027 — accepts NO provider/query-derived prop of any kind. The
// only way to render this component is for a caller to have already
// decided, from PaymentVerificationState.kind === "status" &&
// status === "paid", that it's appropriate
// (#SECURITY-BACKEND-VERIFIED-PAYMENT, enforced one layer up by
// PaymentResultView's own switch). No role="status"/live region of
// its own — PaymentResultView owns the one.
export function PaymentSuccessState({ orderDisplayId, actionSlot }: PaymentSuccessStateProps) {
  return (
    <div className="flex flex-col items-center gap-3 py-8 text-center">
      <p className="text-h3 font-bold text-text-primary">Payment Successful</p>
      {orderDisplayId && <p className="text-body text-text-secondary">{orderDisplayId}</p>}
      {actionSlot && <div className="mt-2">{actionSlot}</div>}
    </div>
  );
}
