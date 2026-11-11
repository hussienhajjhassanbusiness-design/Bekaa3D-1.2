"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ConsentCheckboxGroup, type ConsentKey } from "@/components/checkout/ConsentCheckboxGroup";
import { Alert } from "@/components/feedback/Alert";
import { Button } from "@/components/forms/Button";
import { AUTH_SESSION_QUERY_KEY } from "@/lib/auth/authSession";
import { buildLoginRedirectPath } from "@/lib/auth/returnTo";
import { useCheckoutAttemptTracker } from "@/lib/checkout/checkoutIdempotency";
import { adaptCheckoutRead, type CheckoutResultModel } from "@/lib/checkout/checkoutModel";
import { followPaymentRedirect } from "@/lib/checkout/paymentRedirect";
import { describeOfferCheckoutError, type OfferCheckoutErrorOutcome } from "@/lib/offers/offerErrors";
import { offerKeys } from "@/lib/offers/offerKeys";
import { formatMoney } from "@/lib/offers/offerModel";
import type { OfferCheckoutRequestDTO, OfferDetailReadDTO } from "@/lib/offers/offerTypes";
import { useOfferCheckout } from "@/lib/offers/useOffers";
import { formatOrderDateTime } from "@/lib/orders/orderFormat";

type Phase =
  | { kind: "editing" }
  | { kind: "submitting" }
  | { kind: "uncertain"; message: string }
  | { kind: "redirecting"; result: CheckoutResultModel }
  | { kind: "placed"; result: CheckoutResultModel }
  | { kind: "payment-not-started"; message: string; orderId: string | null; orderNumber: string | null }
  | { kind: "already-active"; message: string; resumeUrl: string | null };

// The body is fixed (both consents true, no provider), so one key covers
// every press until the server answers with a final outcome.
const BODY: OfferCheckoutRequestDTO = { accept_terms: true, accept_digital_final_sale: true };

// #FVS-OFFERS-CHECKOUT (phase 6C)
//
// POST /api/v1/me/offers/{id}/checkout for an `accepted` offer. The price is
// the server's agreed amount (the response's order total); nothing here
// computes or overrides a price. Online payment only (the order is STL-only,
// and cash needs every line physical, ADR-024). Same safety rules as cart
// checkout: one in-flight press, an Idempotency-Key bound to the body, an
// unknown outcome locks to a same-key retry, and an online order goes to the
// server's redirect_url as given. The payment result is the order page's
// (FVS-027); the offer becomes `paid` only after the backend verifies it.
export function OfferCheckoutPanel({ offer }: { offer: OfferDetailReadDTO }) {
  const queryClient = useQueryClient();
  const checkout = useOfferCheckout(offer.id);
  const tracker = useCheckoutAttemptTracker<OfferCheckoutRequestDTO>();
  const inFlight = useRef(false);
  const focusRef = useRef<HTMLHeadingElement>(null);
  const [consents, setConsents] = useState<Record<ConsentKey, boolean>>({
    acceptTerms: false,
    acceptDigitalFinalSale: false,
    acceptCashTerms: false,
  });
  const [consentErrors, setConsentErrors] = useState<Partial<Record<ConsentKey, string>>>({});
  const [problem, setProblem] = useState<Extract<OfferCheckoutErrorOutcome, { retireKey: boolean }> | null>(null);
  const [phase, setPhase] = useState<Phase>({ kind: "editing" });

  useEffect(() => {
    if (phase.kind !== "editing" && phase.kind !== "submitting") focusRef.current?.focus();
  }, [phase.kind]);

  async function submit() {
    if (inFlight.current) return;
    inFlight.current = true;
    setProblem(null);
    setPhase({ kind: "submitting" });
    try {
      const key = tracker.keyFor(BODY);
      const result = adaptCheckoutRead(await checkout.mutateAsync(key));
      tracker.retire();
      if (result.next === "online-redirect") {
        setPhase({ kind: "redirecting", result });
        followPaymentRedirect(result.payment!.redirectUrl!);
      } else {
        setPhase({ kind: "placed", result });
      }
    } catch (error) {
      const outcome = describeOfferCheckoutError(error);
      if (outcome.kind === "uncertain") {
        setPhase({ kind: "uncertain", message: outcome.message });
      } else if (outcome.kind === "payment-not-started") {
        tracker.retire();
        void queryClient.invalidateQueries({ queryKey: offerKeys.root });
        setPhase({ kind: "payment-not-started", message: outcome.message, orderId: outcome.orderId, orderNumber: outcome.orderNumber });
      } else if (outcome.kind === "already-active") {
        tracker.retire();
        setPhase({ kind: "already-active", message: outcome.message, resumeUrl: outcome.resumeUrl });
      } else {
        if (outcome.retireKey) tracker.retire();
        if (outcome.refetchOffer) void queryClient.invalidateQueries({ queryKey: offerKeys.detail(offer.id) });
        if (outcome.refetchAuth) void queryClient.invalidateQueries({ queryKey: AUTH_SESSION_QUERY_KEY });
        setProblem(outcome);
        setPhase({ kind: "editing" });
      }
    } finally {
      inFlight.current = false;
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    const errors: Partial<Record<ConsentKey, string>> = {};
    if (!consents.acceptTerms) errors.acceptTerms = "Please accept the terms of sale to check out.";
    if (!consents.acceptDigitalFinalSale) errors.acceptDigitalFinalSale = "Please confirm you understand that STL files are final sale.";
    setConsentErrors(errors);
    if (Object.keys(errors).length > 0) return;
    void submit();
  }

  const heading = (text: string) => (
    <h3 ref={focusRef} tabIndex={-1} className="text-h3 font-semibold text-text-primary outline-none">
      {text}
    </h3>
  );
  const orderLink = (orderId: string | null) =>
    orderId ? (
      <Link href={`/account/orders/${encodeURIComponent(orderId)}`} className="font-semibold text-brand-dark-green underline">
        View order
      </Link>
    ) : (
      <Link href="/account/orders" className="font-semibold text-brand-dark-green underline">
        View your orders
      </Link>
    );

  let content;
  if (phase.kind === "redirecting") {
    content = (
      <div role="status" className="flex flex-col items-start gap-3">
        <p className="text-body text-text-primary">
          Order <span className="font-semibold">{phase.result.orderNumber}</span> is awaiting payment. Taking you to the payment
          page…
        </p>
        <a href={phase.result.payment?.redirectUrl ?? ""} className="font-semibold text-brand-dark-green underline">
          Continue to payment
        </a>
      </div>
    );
  } else if (phase.kind === "placed") {
    content = (
      <div className="flex flex-col items-start gap-3">
        {heading("Your order is awaiting payment")}
        <p className="text-body text-text-primary">
          Order <span className="font-semibold">{phase.result.orderNumber}</span>, total{" "}
          <span className="font-semibold">
            {formatMoney({ amount_cents: phase.result.total.amountCents, currency: phase.result.total.currency })}
          </span>
          .
        </p>
        <p role="alert" className="rounded-md border-l-4 border-l-warning bg-warning-bg p-3 text-body text-text-primary">
          The payment page isn&apos;t available right now, so nothing has been charged. You can retry the payment from the order
          page.
        </p>
        {orderLink(phase.result.orderId)}
      </div>
    );
  } else if (phase.kind === "payment-not-started") {
    content = (
      <div className="flex flex-col items-start gap-3">
        {heading("Payment not started")}
        <p className="text-body text-text-primary">{phase.message}</p>
        {phase.orderNumber && (
          <p className="text-body text-text-primary">
            Order number <span className="font-semibold">{phase.orderNumber}</span>
          </p>
        )}
        <p className="text-body text-text-secondary">You can retry the payment from the order page.</p>
        {orderLink(phase.orderId)}
      </div>
    );
  } else if (phase.kind === "already-active") {
    content = (
      <div className="flex flex-col items-start gap-3">
        {heading("Payment already in progress")}
        <p className="text-body text-text-primary">{phase.message}</p>
        {phase.resumeUrl ? (
          <Button type="button" onClick={() => followPaymentRedirect(phase.resumeUrl!)}>
            Continue to payment
          </Button>
        ) : null}
        {orderLink(null)}
      </div>
    );
  } else if (phase.kind === "uncertain") {
    content = (
      <div className="flex flex-col items-start gap-3">
        {heading("Checking your order")}
        <p role="alert" className="text-body text-text-primary">
          {phase.message}
        </p>
        <Button type="button" onClick={() => void submit()}>
          Try again
        </Button>
      </div>
    );
  } else {
    const submitting = phase.kind === "submitting";
    content = (
      <form noValidate onSubmit={handleSubmit} className="flex flex-col gap-4">
        <p className="text-body text-text-primary">
          Agreed price:{" "}
          <span className="font-semibold">{offer.agreed_amount ? formatMoney(offer.agreed_amount) : formatMoney(offer.current_amount)}</span>
          . Paid online; the STL file is delivered by email after payment.
        </p>
        {offer.checkout_expires_at && (
          <p className="text-body text-text-secondary">
            Check out by <time dateTime={offer.checkout_expires_at}>{formatOrderDateTime(offer.checkout_expires_at)}</time> to
            keep this price.
          </p>
        )}
        {problem && (
          <div className="flex flex-col items-start gap-2">
            <Alert variant="error" message={problem.message} />
            {problem.kind === "session-expired" && (
              <Link
                href={buildLoginRedirectPath(`/account/offers/${offer.id}`)}
                className="font-semibold text-brand-dark-green underline"
              >
                Sign in again
              </Link>
            )}
            {problem.kind === "verify-email" && (
              <Link href="/verify-email/resend" className="font-semibold text-brand-dark-green underline">
                Resend the verification email
              </Link>
            )}
            {problem.kind === "owned" && orderLink(null)}
          </div>
        )}
        <ConsentCheckboxGroup
          showDigital
          showCash={false}
          values={consents}
          onChange={(key, checked) => {
            setConsents((current) => ({ ...current, [key]: checked }));
            setConsentErrors((current) => ({ ...current, [key]: undefined }));
          }}
          errors={consentErrors}
          disabled={submitting}
        />
        <div>
          <Button type="submit" isLoading={submitting} disabled={submitting}>
            Check out and pay
          </Button>
        </div>
      </form>
    );
  }

  return (
    <section aria-labelledby="offer-checkout-heading" className="flex flex-col gap-3 rounded-md border border-border-default bg-white p-4">
      <h2 id="offer-checkout-heading" className="text-h3 font-semibold text-text-primary">
        Check out at the agreed price
      </h2>
      {content}
    </section>
  );
}
