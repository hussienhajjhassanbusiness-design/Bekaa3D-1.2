import type { ReactNode } from "react";
import type { PaymentVerificationState } from "@/lib/payment/paymentStatusModel";
import { PaymentPendingState } from "./PaymentPendingState";
import { PaymentSuccessState } from "./PaymentSuccessState";
import { PaymentFailedState } from "./PaymentFailedState";
import { PaymentExpiredState } from "./PaymentExpiredState";
import { PaymentVerificationTimeoutState } from "./PaymentVerificationTimeoutState";
import { PaymentVerificationErrorState } from "./PaymentVerificationErrorState";

export interface PaymentResultViewProps {
  verificationState: PaymentVerificationState;
  orderDisplayId?: string;
  successActionSlot?: ReactNode;
  failedActionSlot?: ReactNode;
  expiredActionSlot?: ReactNode;
  onRetryTimeout?: () => void;
  onRetryError?: () => void;
}

// #SECURITY-BACKEND-VERIFIED-PAYMENT
//
// A pure switch over `verificationState` — accepts NO raw provider/
// query prop of any kind, so there is nothing for a future caller to
// even mistakenly wire a query-string value into. Owns the ONE
// aria-live="polite" region wrapping whichever state renders; none of
// the individual state components carries its own live region, so
// there is never a nested/duplicate announcement.
export function PaymentResultView({
  verificationState,
  orderDisplayId,
  successActionSlot,
  failedActionSlot,
  expiredActionSlot,
  onRetryTimeout,
  onRetryError,
}: PaymentResultViewProps) {
  return <div aria-live="polite">{renderState(verificationState, { orderDisplayId, successActionSlot, failedActionSlot, expiredActionSlot, onRetryTimeout, onRetryError })}</div>;
}

function renderState(
  state: PaymentVerificationState,
  opts: {
    orderDisplayId?: string;
    successActionSlot?: ReactNode;
    failedActionSlot?: ReactNode;
    expiredActionSlot?: ReactNode;
    onRetryTimeout?: () => void;
    onRetryError?: () => void;
  }
) {
  switch (state.kind) {
    case "verifying":
      return <PaymentPendingState />;
    case "timeout":
      return <PaymentVerificationTimeoutState onRetry={opts.onRetryTimeout ?? (() => {})} />;
    case "network-error":
      return <PaymentVerificationErrorState onRetry={opts.onRetryError ?? (() => {})} />;
    case "status":
      switch (state.status) {
        case "pending":
        case "processing":
          return <PaymentPendingState />;
        case "paid":
          return <PaymentSuccessState orderDisplayId={opts.orderDisplayId} actionSlot={opts.successActionSlot} />;
        case "failed":
          return <PaymentFailedState actionSlot={opts.failedActionSlot} />;
        case "expired":
          return <PaymentExpiredState actionSlot={opts.expiredActionSlot} />;
      }
  }
}
