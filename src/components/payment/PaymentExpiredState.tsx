import type { ReactNode } from "react";

export interface PaymentExpiredStateProps {
  actionSlot?: ReactNode;
}

// #FVS027 — kept distinct from PaymentFailedState's copy. Never
// claims a provider-specific reason.
export function PaymentExpiredState({ actionSlot }: PaymentExpiredStateProps) {
  return (
    <div className="flex flex-col items-center gap-3 py-8 text-center">
      <p className="text-h3 font-bold text-text-primary">Your payment session expired.</p>
      <p className="text-body text-text-secondary">You have not been charged. You can start again.</p>
      {actionSlot && <div className="mt-2">{actionSlot}</div>}
    </div>
  );
}
