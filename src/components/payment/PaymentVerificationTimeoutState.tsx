import { Button } from "@/components/forms/Button";

export interface PaymentVerificationTimeoutStateProps {
  onRetry: () => void;
}

// #FVS027 — a local-poller-stopped state, never dressed up as a
// payment outcome. "We're still confirming" is explicitly NOT failure
// language — the frontend stopped polling, the payment itself was
// never declared failed.
export function PaymentVerificationTimeoutState({ onRetry }: PaymentVerificationTimeoutStateProps) {
  return (
    <div className="flex flex-col items-center gap-3 py-8 text-center">
      <p className="text-body text-text-primary">We&apos;re still confirming your payment.</p>
      <p className="text-caption text-text-secondary">This is taking longer than usual.</p>
      <Button type="button" onClick={onRetry}>
        Check again
      </Button>
    </div>
  );
}
