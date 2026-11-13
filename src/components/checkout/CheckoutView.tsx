"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Alert } from "@/components/feedback/Alert";
import { EmptyState } from "@/components/feedback/EmptyState";
import { Button, buttonLinkClassName } from "@/components/forms/Button";
import { TextAreaField } from "@/components/forms/TextAreaField";
import { Container } from "@/components/ui/Container";
import { Icon } from "@/components/ui/Icon";
import { addressKeys } from "@/lib/addresses/addressKeys";
import { useAddresses } from "@/lib/addresses/useAddresses";
import { AUTH_SESSION_QUERY_KEY } from "@/lib/auth/authSession";
import { useAuth } from "@/lib/auth/AuthProvider";
import { buildLoginRedirectPath } from "@/lib/auth/returnTo";
import { cartKeys } from "@/lib/cart/cartKeys";
import { UNNAMED_PRODUCT, type CartModel } from "@/lib/cart/cartModel";
import { useCart } from "@/lib/cart/useCart";
import { FULFILLMENT_COPY, refusalReasonText } from "@/lib/checkout/checkoutCopy";
import { cashOption, checkoutGate, pickupOption } from "@/lib/checkout/checkoutEligibility";
import { describeCheckoutError, type CheckoutErrorOutcome } from "@/lib/checkout/checkoutErrors";
import { useCheckoutAttemptTracker } from "@/lib/checkout/checkoutIdempotency";
import { adaptCheckoutRead, type CheckoutResultModel } from "@/lib/checkout/checkoutModel";
import {
  EMPTY_CHECKOUT_FORM,
  MAX_CUSTOMER_NOTE,
  buildCheckoutRequest,
  mergeAcceptedPrices,
  validateCheckoutForm,
  type AcceptedPrice,
  type CheckoutFieldErrors,
  type CheckoutFormState,
} from "@/lib/checkout/checkoutPayload";
import type { CheckoutRequestDTO, FulfillmentMethod, PaymentMethod } from "@/lib/checkout/checkoutTypes";
import { followPaymentRedirect } from "@/lib/checkout/paymentRedirect";
import { usePlaceOrder } from "@/lib/checkout/usePlaceOrder";
import { publicSettingsKeys } from "@/lib/settings/publicSettingsKeys";
import { usePublicSettings } from "@/lib/settings/usePublicSettings";
import { CheckoutConfirmation } from "./CheckoutConfirmation";
import { CheckoutDisabledBanner } from "./CheckoutDisabledBanner";
import { CheckoutItems } from "./CheckoutItems";
import { CheckoutLineIssues } from "./CheckoutLineIssues";
import { CheckoutStepHeading } from "./CheckoutStepHeading";
import { STEP_CARD_CLASSES } from "./choiceCardStyles";
import { ConsentCheckboxGroup, type ConsentKey } from "./ConsentCheckboxGroup";
import { FulfillmentSection } from "./FulfillmentSection";
import { PaymentMethodSection } from "./PaymentMethodSection";
import { PriceChangeConflictBanner } from "./PriceChangeConflictBanner";

type Phase =
  | { kind: "editing" }
  | { kind: "submitting" }
  // The outcome is unknown: the form is locked to this exact body, and the
  // only action is a retry with the same body (so the same key).
  | { kind: "uncertain"; body: CheckoutRequestDTO; message: string }
  | { kind: "placed"; result: CheckoutResultModel }
  | { kind: "redirecting"; result: CheckoutResultModel }
  | {
      kind: "payment-not-started";
      orderId: string | null;
      orderNumber: string | null;
      message: string;
    };

const VALIDATION_SUMMARY = "Please check the highlighted details before placing your order.";
// Inline text links on checkout states (primary ink, underlined, 44px row).
const TEXT_LINK_CLASS =
  "inline-flex min-h-11 items-center gap-2 rounded-sm font-semibold text-primary underline decoration-1 underline-offset-4 hover:decoration-2";
// A state panel that replaces the form (result, unknown outcome, guards).
const STATE_CARD_CLASS =
  "flex max-w-3xl flex-col items-start gap-4 rounded-card border border-outline-variant/30 bg-surface-container-lowest p-5 shadow-sm tablet:p-8";

function cartNames(cart: CartModel): Record<string, string> {
  return Object.fromEntries(cart.lines.map((line) => [line.productId, line.name ?? UNNAMED_PRODUCT]));
}

// #FVS026-CHECKOUT-VIEW
//
// /checkout against the real POST /api/v1/checkout (backend 2dfb27b).
// Reuses the canonical cart query (FVS-025), the canonical address-book
// query (FVS-023) and the public-settings query; keeps no cart or address
// store of its own. Safety rules:
//   - one in-flight submission at a time (a ref guard plus a disabled
//     button), and the Idempotency-Key is bound to the exact body
//     (checkoutIdempotency.ts), so a retry can never place a second order;
//   - only a 201 shows a result; every failure keeps the form and the cart
//     (the server never touches the cart on a refusal);
//   - an unknown outcome locks the form and offers only a same-key retry;
//   - a price change is never accepted for the customer;
//   - an online order goes to the server's redirect_url as given, and its
//     payment result is not shown here (FVS-027).
export function CheckoutView() {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const cartQuery = useCart();
  const addressesQuery = useAddresses();
  const settingsQuery = usePublicSettings();
  const placeOrder = usePlaceOrder();
  const tracker = useCheckoutAttemptTracker();
  const inFlight = useRef(false);
  const focusRef = useRef<HTMLHeadingElement>(null);
  const problemRef = useRef<HTMLDivElement>(null);

  const [form, setForm] = useState<CheckoutFormState>(EMPTY_CHECKOUT_FORM);
  const [fieldErrors, setFieldErrors] = useState<CheckoutFieldErrors>({});
  const [validationFailed, setValidationFailed] = useState(false);
  const [acceptedPrices, setAcceptedPrices] = useState<AcceptedPrice[]>([]);
  const [priceAccepted, setPriceAccepted] = useState(false);
  const [problem, setProblem] = useState<CheckoutErrorOutcome | null>(null);
  const [phase, setPhase] = useState<Phase>({ kind: "editing" });
  const [submittedNames, setSubmittedNames] = useState<Record<string, string>>({});

  const settings = settingsQuery.data;
  const pickup = pickupOption(settings);
  const cart = cartQuery.data ?? null;
  const names = { ...submittedNames, ...(cart ? cartNames(cart) : {}) };

  // Move focus to whatever replaced the form, or to the new problem.
  useEffect(() => {
    if (phase.kind === "placed" || phase.kind === "uncertain" || phase.kind === "payment-not-started") {
      focusRef.current?.focus();
    }
  }, [phase.kind]);
  useEffect(() => {
    if (problem || validationFailed) {
      problemRef.current?.focus();
    }
  }, [problem, validationFailed]);

  function applyEffects(outcome: CheckoutErrorOutcome) {
    if (outcome.refetchCart) void queryClient.invalidateQueries({ queryKey: cartKeys.root });
    if (outcome.refetchSettings) void queryClient.invalidateQueries({ queryKey: publicSettingsKeys.root });
    if (outcome.refetchAddresses) void queryClient.invalidateQueries({ queryKey: addressKeys.root });
    if (outcome.refetchAuth) void queryClient.invalidateQueries({ queryKey: AUTH_SESSION_QUERY_KEY });
  }

  async function submit(body: CheckoutRequestDTO) {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    setProblem(null);
    setValidationFailed(false);
    setPhase({ kind: "submitting" });
    try {
      const key = tracker.keyFor(body);
      const result = adaptCheckoutRead(await placeOrder.mutateAsync({ body, idempotencyKey: key }));
      tracker.retire();
      if (result.next === "online-redirect" && result.droppedProductIds.length === 0) {
        setPhase({ kind: "redirecting", result });
        followPaymentRedirect(result.payment!.redirectUrl!);
      } else {
        setPhase({ kind: "placed", result });
      }
    } catch (error) {
      const outcome = describeCheckoutError(error, {
        cashMaxOrderTotal: settings?.cashMaxOrderTotal ?? null,
      });
      if (outcome.retireKey) tracker.retire();
      applyEffects(outcome);
      if (outcome.kind === "payment-not-started") {
        setPhase({
          kind: "payment-not-started",
          orderId: outcome.orderId,
          orderNumber: outcome.orderNumber,
          message: outcome.message,
        });
      } else if (outcome.uncertain) {
        setPhase({ kind: "uncertain", body, message: outcome.message });
      } else {
        setPhase({ kind: "editing" });
        setProblem(outcome);
        if (outcome.kind === "fields") setFieldErrors(outcome.fieldErrors);
        if (outcome.kind === "price-changed") setPriceAccepted(false);
      }
    } finally {
      inFlight.current = false;
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>, currentCart: CartModel) {
    event.preventDefault();
    if (inFlight.current) {
      return;
    }
    const errors = validateCheckoutForm(form, currentCart, {
      cashOffered: cashOption(currentCart, settings).offered,
      pickupAvailable: pickup.available,
    });
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) {
      setProblem(null);
      setValidationFailed(true);
      return;
    }
    setSubmittedNames(cartNames(currentCart));
    void submit(buildCheckoutRequest(form, currentCart, acceptedPrices));
  }

  function handleAcceptPrices() {
    if (problem?.kind !== "price-changed") return;
    setAcceptedPrices((previous) =>
      mergeAcceptedPrices(
        previous,
        problem.changes.map((change) => ({
          productId: change.productId,
          amountCents: change.newAmountCents,
          currency: change.currency,
        }))
      )
    );
    setPriceAccepted(true);
  }

  function update(patch: Partial<CheckoutFormState>) {
    setForm((current) => ({ ...current, ...patch }));
  }

  function chooseFulfillment(method: FulfillmentMethod) {
    const defaultAddress = addressesQuery.data?.find((address) => address.isDefault);
    update({
      fulfillment: method,
      addressId: method === "delivery" ? (form.addressId ?? defaultAddress?.id ?? null) : form.addressId,
    });
  }

  // Redesign Batch 6: shared 1440px Container; the page's single h1
  // (display role, as the cart) and a one-line description in every state.
  const page = (content: ReactNode) => (
    <Container className="flex flex-col gap-8 py-10 tablet:py-12 desktop:py-16">
      <div className="flex max-w-2xl flex-col gap-3">
        <h1 className="font-display text-display text-on-surface">Checkout</h1>
        <p className="text-body-md text-on-surface-variant">
          Choose how you&apos;ll receive your order and how you&apos;ll pay, then confirm and place it.
        </p>
      </div>
      {content}
    </Container>
  );

  // --- results that no longer depend on the cart -------------------------
  if (phase.kind === "placed") {
    return page(
      <CheckoutConfirmation
        result={phase.result}
        names={names}
        pickup={pickup}
        headingRef={focusRef}
        onContinueToPayment={() => {
          const url = phase.result.payment?.redirectUrl;
          if (phase.result.next === "online-redirect" && url) followPaymentRedirect(url);
        }}
      />
    );
  }
  if (phase.kind === "redirecting") {
    const url = phase.result.payment?.redirectUrl ?? "";
    return page(
      <div role="status" className={STATE_CARD_CLASS}>
        <p className="flex items-start gap-3 text-body-md text-on-surface">
          <Icon name="open-in-new" className="mt-0.5 h-5 w-5 text-primary" />
          <span>
            Order <span className="font-semibold">{phase.result.orderNumber}</span> is awaiting payment. Taking you to
            the payment page…
          </span>
        </p>
        <a href={url} className={TEXT_LINK_CLASS}>
          Continue to payment
        </a>
      </div>
    );
  }
  if (phase.kind === "payment-not-started") {
    return page(
      <section aria-labelledby="checkout-unpaid-heading" className={STATE_CARD_CLASS}>
        <h2
          id="checkout-unpaid-heading"
          ref={focusRef}
          tabIndex={-1}
          className="font-headline text-headline-lg text-on-surface outline-none"
        >
          Payment not started
        </h2>
        <p className="flex items-start gap-3 rounded-card border border-warning-outline bg-warning-container p-4 text-body text-on-warning-container">
          <Icon name="warning" className="h-5 w-5" />
          <span>{phase.message}</span>
        </p>
        {phase.orderNumber && (
          <p className="text-body-md text-on-surface">
            Order number <span className="font-label text-label-caps font-bold">{phase.orderNumber}</span>
          </p>
        )}
        <p className="text-body-md text-on-surface-variant">You can retry the payment from the order page.</p>
        {phase.orderId ? (
          <Link
            href={`/account/orders/${encodeURIComponent(phase.orderId)}`}
            className={buttonLinkClassName("primary")}
          >
            View order
          </Link>
        ) : (
          <Link href="/account/orders" className={buttonLinkClassName("primary")}>
            View your orders
          </Link>
        )}
      </section>
    );
  }

  // --- guards --------------------------------------------------------------
  const authFailed = auth.isError && !auth.user;
  if (authFailed) {
    return page(
      <div className="flex max-w-2xl flex-col items-start gap-4">
        <Alert variant="error" message="We couldn't load your account. Please try again." />
        <Button
          type="button"
          onClick={() =>
            void queryClient.invalidateQueries({
              queryKey: AUTH_SESSION_QUERY_KEY,
            })
          }
        >
          Retry
        </Button>
      </div>
    );
  }
  if (!auth.user) {
    // ProtectedRoute owns the anonymous redirect.
    return page(null);
  }
  if (phase.kind === "uncertain") {
    return page(
      <section aria-labelledby="checkout-uncertain-heading" className={STATE_CARD_CLASS}>
        <h2
          id="checkout-uncertain-heading"
          ref={focusRef}
          tabIndex={-1}
          className="font-headline text-headline-md text-on-surface outline-none"
        >
          Checking your order
        </h2>
        <p
          role="alert"
          className="flex items-start gap-3 rounded-card border border-warning-outline bg-warning-container p-4 text-body text-on-warning-container"
        >
          <Icon name="warning" className="h-5 w-5" />
          <span>{phase.message}</span>
        </p>
        <Button type="button" onClick={() => void submit(phase.body)}>
          Try again
        </Button>
      </section>
    );
  }
  if (!auth.user.emailVerified) {
    return page(
      <div className="flex max-w-2xl flex-col items-start gap-3">
        <Alert variant="info" message="Verify your email address before placing an order. Your cart is saved." />
        <Link href="/verify-email/resend" className={TEXT_LINK_CLASS}>
          Resend the verification email
        </Link>
      </div>
    );
  }
  if (cartQuery.isPending) {
    return page(
      <div role="status" className="grid grid-cols-1 items-start gap-8 desktop:grid-cols-12 desktop:gap-12">
        <span className="sr-only">Loading checkout…</span>
        <div aria-hidden="true" className="flex flex-col gap-6 desktop:col-span-7">
          {[0, 1].map((index) => (
            <div
              key={index}
              className="h-48 animate-pulse rounded-card bg-surface-container-low motion-reduce:animate-none"
            />
          ))}
        </div>
        <div
          aria-hidden="true"
          className="h-72 animate-pulse rounded-panel bg-surface-container-low motion-reduce:animate-none desktop:col-span-5"
        />
      </div>
    );
  }
  if (cartQuery.isError || !cart) {
    return page(
      <div className="flex max-w-2xl flex-col items-start gap-4">
        <Alert variant="error" message="We couldn't load your cart. Please try again." />
        <Button type="button" onClick={() => void cartQuery.refetch()}>
          Retry
        </Button>
      </div>
    );
  }

  const gate = checkoutGate({ user: auth.user, cart, settings });
  if (gate.kind === "empty") {
    return page(
      <div className="flex flex-col items-center gap-4">
        {problem?.kind === "cart-empty" && (
          <CheckoutLineIssues
            message={problem.message}
            items={problem.droppedProductIds.map((productId) => ({
              productId,
              name: names[productId] ?? "An STL file",
            }))}
          />
        )}
        <div className="flex w-full flex-col items-center rounded-card border border-dashed border-outline-variant bg-surface-container-lowest px-4 pb-12">
          <EmptyState message="Your cart is empty, so there's nothing to check out." icon="shopping-cart" />
          <Link href="/shop" className={buttonLinkClassName("primary", "lg")}>
            Browse the shop
          </Link>
        </div>
      </div>
    );
  }
  if (gate.kind === "needs-attention") {
    return page(
      <div className="max-w-3xl">
        <CheckoutLineIssues
          message="Some items in your cart can't be ordered right now. Update your cart to continue:"
          items={gate.lines.map((line) => ({
            productId: line.productId,
            name: line.name ?? UNNAMED_PRODUCT,
            detail: refusalReasonText(line.overCap ? "over_cap" : (line.unpurchasableReason ?? ""), line.maxQuantity),
          }))}
          showCartLink
        />
      </div>
    );
  }
  if (gate.kind === "paused") {
    return page(
      <div className="flex max-w-2xl flex-col items-start gap-3">
        <CheckoutDisabledBanner reason="The shop isn't accepting orders right now. Your cart is saved, so you can check out later." />
        <Link href="/cart" className={TEXT_LINK_CLASS}>
          Back to your cart
        </Link>
      </div>
    );
  }

  // --- the form ------------------------------------------------------------
  const submitting = phase.kind === "submitting";
  const cash = cashOption(cart, settings);
  const priceBlocked = problem?.kind === "price-changed" && !priceAccepted;
  // Step-header decoration only (filled circle + check). Never gates the
  // submit: validateCheckoutForm and the server decide.
  const fulfillmentChosen =
    form.fulfillment === "delivery"
      ? form.addressId !== null
      : form.fulfillment === "pickup" && form.contactPhone.trim() !== "";
  const consentsGiven =
    form.acceptTerms &&
    (!cart.containsDigital || form.acceptDigitalFinalSale) &&
    (form.paymentMethod !== "cash" || form.acceptCashTerms);

  // Redesign Batch 6 (PAGE-SPECS S7): 7/5 split from 1024px — numbered step
  // cards on the left, the order summary on the right, sticky below the
  // 64px sticky header (top-24 = 96px). Below 1024px one column, with the
  // decisions first and the summary + Place order after them (DOM order =
  // visual order = keyboard order at every width).
  return page(
    <form
      noValidate
      onSubmit={(event) => handleSubmit(event, cart)}
      className="grid grid-cols-1 items-start gap-8 desktop:grid-cols-12 desktop:gap-12"
    >
      <div className="flex min-w-0 flex-col gap-6 desktop:col-span-7">
        <div ref={problemRef} tabIndex={-1} className="flex flex-col gap-3 outline-none empty:hidden">
          {validationFailed && <Alert variant="error" message={VALIDATION_SUMMARY} />}
          {problem && (
            <ProblemNotice
              problem={problem}
              names={names}
              priceAccepted={priceAccepted}
              onAcceptPrices={handleAcceptPrices}
            />
          )}
        </div>

        {cart.containsPhysical ? (
          <div className={STEP_CARD_CLASSES}>
            <FulfillmentSection
              value={form.fulfillment}
              onChange={chooseFulfillment}
              addresses={addressesQuery.data ?? []}
              addressesLoading={addressesQuery.isPending}
              addressesError={addressesQuery.isError}
              onRetryAddresses={() => void addressesQuery.refetch()}
              addressId={form.addressId}
              onAddressChange={(addressId) => update({ addressId })}
              contactPhone={form.contactPhone}
              onContactPhoneChange={(contactPhone) => update({ contactPhone })}
              pickup={pickup}
              errors={fieldErrors}
              disabled={submitting}
              step={1}
              complete={fulfillmentChosen}
            />
            {cart.containsDigital && (
              <p className="mt-6 flex items-start gap-2 rounded-control bg-surface-container-low px-3 py-2 text-caption text-on-surface-variant">
                <Icon name="mail" className="mt-px h-4 w-4 text-primary" />
                <span>{FULFILLMENT_COPY.mixedDigital}</span>
              </p>
            )}
          </div>
        ) : (
          <section aria-labelledby="checkout-digital-heading" className={STEP_CARD_CLASSES}>
            <CheckoutStepHeading id="checkout-digital-heading" step={1} title="Delivery" complete />
            <p className="flex items-start gap-3 rounded-control bg-surface-container-low p-4 text-body text-on-surface">
              <Icon name="mail" className="mt-px h-5 w-5 text-primary" />
              <span>{FULFILLMENT_COPY.digitalOnly}</span>
            </p>
          </section>
        )}

        <div className={STEP_CARD_CLASSES}>
          <PaymentMethodSection
            value={form.paymentMethod}
            onChange={(paymentMethod: PaymentMethod) => update({ paymentMethod })}
            cash={cash}
            error={fieldErrors.paymentMethod}
            disabled={submitting}
            step={2}
            complete={form.paymentMethod !== null}
          />
        </div>

        {/* Optional, so not a numbered step; kept in its original place
            between payment and the consents. */}
        <div className={STEP_CARD_CLASSES}>
          <TextAreaField
            label="Order note (optional)"
            hint="Anything we should know about your order."
            maxLength={MAX_CUSTOMER_NOTE}
            value={form.customerNote}
            onChange={(event) => update({ customerNote: event.target.value })}
            error={fieldErrors.customerNote}
            disabled={submitting}
          />
        </div>

        <div className={STEP_CARD_CLASSES}>
          <ConsentCheckboxGroup
            showDigital={cart.containsDigital}
            showCash={form.paymentMethod === "cash"}
            values={form}
            onChange={(key: ConsentKey, checked) => update({ [key]: checked })}
            errors={fieldErrors}
            disabled={submitting}
            step={3}
            complete={consentsGiven}
          />
        </div>
      </div>

      <aside
        aria-labelledby="checkout-items-heading"
        className="flex min-w-0 flex-col gap-4 desktop:sticky desktop:top-24 desktop:col-span-5"
      >
        <CheckoutItems cart={cart}>
          <div className="flex flex-col gap-3">
            <Button
              type="submit"
              size="lg"
              className="w-full"
              isLoading={submitting}
              disabled={submitting || priceBlocked}
            >
              Place order
            </Button>
            {submitting && (
              <p role="status" className="text-center text-caption text-on-surface-variant">
                Placing your order…
              </p>
            )}
            {priceBlocked && (
              <p className="flex items-start gap-2 text-caption text-on-warning-container">
                <Icon name="warning" className="mt-px h-4 w-4" />
                <span>Accept the new prices above before placing your order.</span>
              </p>
            )}
          </div>
        </CheckoutItems>
        <Link href="/cart" className={`${TEXT_LINK_CLASS} self-center text-caption`}>
          <Icon name="arrow-back" className="h-4 w-4" />
          Back to your cart
        </Link>
      </aside>
    </form>
  );
}

function ProblemNotice({
  problem,
  names,
  priceAccepted,
  onAcceptPrices,
}: {
  problem: CheckoutErrorOutcome;
  names: Readonly<Record<string, string>>;
  priceAccepted: boolean;
  onAcceptPrices: () => void;
}) {
  switch (problem.kind) {
    case "price-changed":
      return (
        <PriceChangeConflictBanner
          changes={problem.changes}
          names={names}
          accepted={priceAccepted}
          onAccept={onAcceptPrices}
        />
      );
    case "lines-refused":
      return (
        <CheckoutLineIssues
          message={problem.message}
          items={problem.lines.map((line) => ({
            productId: line.productId,
            name: names[line.productId] ?? UNNAMED_PRODUCT,
            detail: refusalReasonText(line.reason, line.maxQuantity),
          }))}
          showCartLink
        />
      );
    case "already-owned":
      return (
        <CheckoutLineIssues
          message={problem.message}
          items={problem.productIds.map((productId) => ({
            productId,
            name: names[productId] ?? UNNAMED_PRODUCT,
          }))}
          showCartLink
        />
      );
    case "session-expired":
      return (
        <div className="flex flex-col items-start gap-2">
          <Alert variant="error" message={problem.message} />
          <Link href={buildLoginRedirectPath("/checkout")} className={TEXT_LINK_CLASS}>
            Log in again
          </Link>
        </div>
      );
    default:
      return <Alert variant="error" message={problem.message} />;
  }
}
