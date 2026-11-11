"use client";

import Link from "next/link";
import { useId, useRef, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Alert } from "@/components/feedback/Alert";
import { Button } from "@/components/forms/Button";
import { MoneyInput } from "@/components/forms/MoneyInput";
import { TextAreaField } from "@/components/forms/TextAreaField";
import { useAuth } from "@/lib/auth/AuthProvider";
import { AUTH_SESSION_QUERY_KEY } from "@/lib/auth/authSession";
import { buildLoginRedirectPath } from "@/lib/auth/returnTo";
import { productsKeys } from "@/lib/catalog/productsApi";
import { describeOfferError, OFFER_MESSAGES, type OfferErrorOutcome } from "@/lib/offers/offerErrors";
import { describeOfferStatus, isLiveOffer } from "@/lib/offers/offerModel";
import { MAX_OFFER_MESSAGE, OFFER_CURRENCY } from "@/lib/offers/offerTypes";
import { useCreateOffer, useMyOffersForProduct } from "@/lib/offers/useOffers";

export interface MakeOfferPanelProps {
  productId: string;
  productName: string;
  // ProductDetail.capabilities.can_offer: the backend's own product-level
  // answer (an available, listed STL). Never inferred from the product type.
  canOffer: boolean;
  returnToPath: string;
}

// #FVS-OFFERS-MAKE-OFFER (phase 6C) — POST /api/v1/offers on the product page.
// - capability false: renders nothing, so no request can be sent.
// - anonymous: a login-redirect link (the shared safe returnTo helper).
// - unverified: the backend would answer 403 EMAIL_VERIFICATION_REQUIRED.
// - verified: one small read of the customer's own offers on this product
//   (`product_id` filter); a live one is linked instead of a doomed form.
// The minimum offer is a server setting that isn't public, so the floor is
// enforced by the server's 422 OFFER_BELOW_MINIMUM, whose `minimum` is shown.
export function MakeOfferPanel({ productId, productName, canOffer, returnToPath }: MakeOfferPanelProps) {
  const { user, isLoading } = useAuth();
  if (!canOffer || isLoading) return null;

  if (!user) {
    return (
      <a href={buildLoginRedirectPath(returnToPath)} className="inline-block rounded-md border border-brand-dark-green px-4 py-2 text-brand-dark-green">
        Make an offer
      </a>
    );
  }
  if (!user.emailVerified) {
    return (
      <p className="text-body text-text-secondary">
        <Link href="/verify-email/resend" className="text-brand-dark-green underline">
          Verify your email
        </Link>{" "}
        to make an offer.
      </p>
    );
  }
  return <VerifiedMakeOffer productId={productId} productName={productName} returnToPath={returnToPath} />;
}

function VerifiedMakeOffer({ productId, productName, returnToPath }: Omit<MakeOfferPanelProps, "canOffer">) {
  const queryClient = useQueryClient();
  const existing = useMyOffersForProduct(productId, true);
  const create = useCreateOffer();
  const inFlight = useRef(false);
  const formId = useId();
  const toggleId = useId();
  const [open, setOpen] = useState(false);
  const [amountCents, setAmountCents] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [amountError, setAmountError] = useState<string | null>(null);
  const [failure, setFailure] = useState<OfferErrorOutcome | null>(null);
  const [sentId, setSentId] = useState<string | null>(null);

  const live = existing.data?.items.find((offer) => isLiveOffer(offer.status)) ?? null;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    if (amountCents === null || amountCents < 1) {
      setAmountError("Enter the amount you'd like to offer.");
      return;
    }
    inFlight.current = true;
    setAmountError(null);
    setFailure(null);
    try {
      const offer = await create.mutateAsync({ productId, amountCents, message });
      setSentId(offer.id);
      setOpen(false);
      setAmountCents(null);
      setMessage("");
    } catch (error) {
      const outcome = describeOfferError(error, "create");
      if (outcome.refetchAuth) void queryClient.invalidateQueries({ queryKey: AUTH_SESSION_QUERY_KEY });
      if (outcome.refetchProduct) void queryClient.invalidateQueries({ queryKey: productsKeys.root });
      if (outcome.kind === "already-active") void existing.refetch();
      setFailure(outcome);
      if (outcome.field?.name === "amount") setAmountError(outcome.field.message);
    } finally {
      inFlight.current = false;
    }
  }

  return (
    <div className="flex w-full flex-col gap-3">
      {sentId && (
        <p role="status" className="text-body text-text-primary">
          Your offer was sent. We&apos;ll reply before the deadline.{" "}
          <Link href={`/account/offers/${encodeURIComponent(sentId)}`} className="font-semibold text-brand-dark-green underline">
            View your offer
          </Link>
        </p>
      )}

      {live ? (
        !sentId && (
          <p className="text-body text-text-primary">
            You have an offer in progress on this STL ({describeOfferStatus(live.status, "customer").label.toLowerCase()}).{" "}
            <Link href={`/account/offers/${encodeURIComponent(live.id)}`} className="font-semibold text-brand-dark-green underline">
              View your offer
            </Link>
          </p>
        )
      ) : (
        <>
          <div>
            <Button
              id={toggleId}
              type="button"
              variant="secondary"
              aria-expanded={open}
              aria-controls={open ? formId : undefined}
              onClick={() => {
                setOpen((current) => !current);
                setFailure(null);
                setAmountError(null);
              }}
            >
              Make an offer
            </Button>
          </div>
          {open && (
            <form
              id={formId}
              noValidate
              onSubmit={(event) => void handleSubmit(event)}
              aria-label={`Make an offer on ${productName}`}
              className="flex flex-col gap-3 rounded-md border border-border-default bg-white p-4"
            >
              <p className="text-body text-text-secondary">
                Propose a price for this STL. We&apos;ll accept, decline or reply with a counter-offer before the deadline.
              </p>
              <MoneyInput
                label="Your offer"
                currencyLabel={OFFER_CURRENCY}
                valueCents={amountCents}
                onChangeCents={(next) => {
                  setAmountCents(next);
                  setAmountError(null);
                }}
                error={amountError ?? undefined}
              />
              <TextAreaField
                label="Message (optional)"
                maxLength={MAX_OFFER_MESSAGE}
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                error={failure?.field?.name === "message" ? failure.field.message : undefined}
                disabled={create.isPending}
              />
              {failure && failure.field?.name !== "amount" && (
                <div className="flex flex-col items-start gap-2">
                  <Alert variant="error" message={failure.message} />
                  {(failure.kind === "already-active" || failure.message === OFFER_MESSAGES.uncertainCreate) && (
                    <Link href="/account/offers" className="font-semibold text-brand-dark-green underline">
                      View your offers
                    </Link>
                  )}
                  {failure.kind === "session-expired" && (
                    <Link href={buildLoginRedirectPath(returnToPath)} className="font-semibold text-brand-dark-green underline">
                      Sign in again
                    </Link>
                  )}
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                <Button type="submit" isLoading={create.isPending} disabled={create.isPending}>
                  Send offer
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={create.isPending}
                  onClick={() => {
                    setOpen(false);
                    setFailure(null);
                    setAmountError(null);
                    document.getElementById(toggleId)?.focus();
                  }}
                >
                  Cancel
                </Button>
              </div>
            </form>
          )}
        </>
      )}
    </div>
  );
}
