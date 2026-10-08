import { Button } from "@/components/forms/Button";

export interface PaymentVerificationErrorStateProps {
  onRetry: () => void;
}

// #FVS027 — a transient polling/network error means "verification
// temporarily unavailable," never "payment failed." Never renders a
// raw server/network exception message.
export function PaymentVerificationErrorState({ onRetry }: PaymentVerificationErrorStateProps) {
  return (
    <div className="flex flex-col items-center gap-3 py-8 text-center">
      <p className="text-body text-text-primary">Verification is temporarily unavailable.</p>
      <p className="text-caption text-text-secondary">We couldn&apos;t check your payment status just now.</p>
      <Button type="button" onClick={onRetry}>
        Retry
      </Button>
    </div>
  );
}
