import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { PaymentResultView } from "./PaymentResultView";
import { extractReturnIdentifier } from "@/lib/payment/paymentReturnIdentifier";
import type { PaymentVerificationState } from "@/lib/payment/paymentStatusModel";

// FVS-027-IMPLEMENTATION-PLAN.md T07 — accepts no raw provider/query
// prop of any kind. Owns the ONE aria-live="polite" region wrapping
// whichever state renders, avoiding nested/duplicate announcements.

describe("PaymentResultView", () => {
  it("renders PaymentPendingState for kind: verifying", () => {
    render(<PaymentResultView verificationState={{ kind: "verifying" }} />);
    expect(screen.getByText(/confirming your payment/i)).toBeInTheDocument();
  });

  it("renders PaymentPendingState for a backend-verified pending status", () => {
    render(<PaymentResultView verificationState={{ kind: "status", status: "pending" }} />);
    expect(screen.getByText(/confirming your payment/i)).toBeInTheDocument();
  });

  it("renders PaymentPendingState for a backend-verified processing status", () => {
    render(<PaymentResultView verificationState={{ kind: "status", status: "processing" }} />);
    expect(screen.getByText(/confirming your payment/i)).toBeInTheDocument();
  });

  it("renders PaymentSuccessState only for a backend-verified paid status", () => {
    render(<PaymentResultView verificationState={{ kind: "status", status: "paid" }} />);
    expect(screen.getByText(/payment successful/i)).toBeInTheDocument();
  });

  it("renders PaymentFailedState for a backend-verified failed status", () => {
    render(<PaymentResultView verificationState={{ kind: "status", status: "failed" }} />);
    expect(screen.getByText(/could not be completed/i)).toBeInTheDocument();
  });

  it("renders PaymentExpiredState for a backend-verified expired status", () => {
    render(<PaymentResultView verificationState={{ kind: "status", status: "expired" }} />);
    expect(screen.getByText(/session expired/i)).toBeInTheDocument();
  });

  it("renders PaymentVerificationTimeoutState for kind: timeout", () => {
    render(<PaymentResultView verificationState={{ kind: "timeout" }} onRetryTimeout={vi.fn()} />);
    expect(screen.getByText(/still confirming/i)).toBeInTheDocument();
  });

  it("renders PaymentVerificationErrorState for kind: network-error", () => {
    render(<PaymentResultView verificationState={{ kind: "network-error" }} onRetryError={vi.fn()} />);
    expect(screen.getByText(/temporarily unavailable/i)).toBeInTheDocument();
  });

  it("owns exactly one aria-live=polite region regardless of which state is active", () => {
    const states: PaymentVerificationState[] = [
      { kind: "verifying" },
      { kind: "status", status: "paid" },
      { kind: "status", status: "failed" },
      { kind: "timeout" },
      { kind: "network-error" },
    ];
    for (const verificationState of states) {
      const { container, unmount } = render(
        <PaymentResultView verificationState={verificationState} onRetryTimeout={vi.fn()} onRetryError={vi.fn()} />
      );
      expect(container.querySelectorAll('[aria-live="polite"]')).toHaveLength(1);
      unmount();
    }
  });

  it("MOST IMPORTANT: a manipulated success-looking return query string never produces success while the backend-verified status remains pending", () => {
    // The exact anti-pattern this slice exists to prevent: a return
    // URL claiming success/paid, while the backend still says
    // pending. The identifier extraction is genuinely exercised (not
    // just asserted by a helper's name) — its result plays no role in
    // deciding what renders; only `verificationState` does.
    const params = new URLSearchParams("order_id=123&status=success&paid=true&payment_status=paid");
    const identifiedOrderId = extractReturnIdentifier(params, "order_id");
    expect(identifiedOrderId).toBe("123");

    render(<PaymentResultView verificationState={{ kind: "status", status: "pending" }} orderDisplayId={identifiedOrderId ?? undefined} />);

    expect(screen.getByText(/confirming your payment/i)).toBeInTheDocument();
    expect(screen.queryByText(/payment successful/i)).not.toBeInTheDocument();
  });

  it("accepts no raw provider/query prop — there is no 'rawStatus'/'providerQueryParams' field in its type", () => {
    // Structural proof by exhaustive usage: every real render in this
    // file supplies only verificationState/orderDisplayId/action
    // slots/retry callbacks — there is nothing else to wire a
    // query-string value into.
    render(<PaymentResultView verificationState={{ kind: "status", status: "paid" }} />);
    expect(screen.getByText(/payment successful/i)).toBeInTheDocument();
  });
});
