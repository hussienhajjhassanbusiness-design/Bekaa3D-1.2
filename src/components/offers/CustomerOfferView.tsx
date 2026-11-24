"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { Alert } from "@/components/feedback/Alert";
import {
  ACCOUNT_CARD,
  AccountBackLink,
  AccountErrorCard,
  AccountListSkeleton,
  AccountSection,
  AccountSessionCard,
} from "@/components/account/accountUi";
import { EmptyState } from "@/components/feedback/EmptyState";
import { Button, buttonLinkClassName } from "@/components/forms/Button";
import { Icon } from "@/components/ui/Icon";
import { PageHeader } from "@/components/ui/PageHeader";
import { AUTH_SESSION_QUERY_KEY } from "@/lib/auth/authSession";
import { buildLoginRedirectPath } from "@/lib/auth/returnTo";
import { describeOfferError, type OfferErrorOutcome } from "@/lib/offers/offerErrors";
import { offerKeys } from "@/lib/offers/offerKeys";
import { allowedMoves, describeOfferStatus, offerProductName } from "@/lib/offers/offerModel";
import type { OfferMove } from "@/lib/offers/offerTypes";
import { useAnswerOffer, useMyOffer, type CustomerOfferAnswer } from "@/lib/offers/useOffers";
import { isOrderId } from "@/lib/orders/orderModel";
import { OfferCheckoutPanel } from "./OfferCheckoutPanel";
import { OfferFacts } from "./OfferFacts";
import { OfferHistory } from "./OfferHistory";
import { OfferMoveDialog, type OfferMoveValues } from "./OfferMoveDialog";

const MOVE_LABELS: Record<OfferMove, string> = {
  accept: "Accept this amount",
  counter: "Counter-offer",
  withdraw: "Withdraw offer",
  reject: "Reject",
};

const SUCCESS: Partial<Record<OfferMove, string>> = {
  accept: "You accepted the offer. Check out below to buy at the agreed price.",
  counter: "Your counter-offer was sent. We'll reply before the deadline.",
  withdraw: "You withdrew your offer.",
};

// #FVS-OFFERS-CUSTOMER-DETAIL (phase 6C) — /account/offers/[id]
// (GET /api/v1/me/offers/{id}). The buttons are exactly the server's
// `allowed_actions`; the checkout panel appears only for `accepted`.
// An unknown id, a malformed id and another customer's offer are the same
// "not found" (the backend's own 404 hides ownership).
//
// Batch 7 (DERIVED: account shell + PageHeader + Stitch C3 language). The
// h1 and the status pill share one parent (PageHeader `meta`); facts card,
// then the reply actions (still exactly `allowed_actions`, one primary),
// the checkout panel for `accepted`, and the history timeline last.
// Handlers, guards, error mapping and query invalidation are unchanged.
export function CustomerOfferView({ offerId }: { offerId: string }) {
  const validId = isOrderId(offerId);
  const queryClient = useQueryClient();
  const query = useMyOffer(offerId, validId);
  const answer = useAnswerOffer(offerId);
  const inFlight = useRef(false);
  const [move, setMove] = useState<OfferMove | null>(null);
  const [failure, setFailure] = useState<OfferErrorOutcome | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  if (!validId) return <OfferNotFound />;
  if (query.isPending) {
    return (
      <>
        <PageHeader eyebrow="Offer details" title="Offer" />
        <AccountListSkeleton label="Loading this offer…" rows={2} />
      </>
    );
  }
  if (query.isError) {
    const e = query.error;
    if (e.kind === "http" && (e.status === 404 || e.status === 422)) return <OfferNotFound />;
    if (e.kind === "http" && e.status === 401) {
      return (
        <>
          <PageHeader eyebrow="Offer details" title="Offer" />
          <AccountSessionCard
            message="Your session has expired. Please sign in again to see your offers."
            href={buildLoginRedirectPath(`/account/offers/${offerId}`)}
          />
        </>
      );
    }
    return (
      <>
        <PageHeader eyebrow="Offer details" title="Offer" />
        <AccountErrorCard
          message="We couldn't load this offer. Please try again."
          onRetry={() => void query.refetch()}
        />
      </>
    );
  }

  const offer = query.data;
  const status = describeOfferStatus(offer.status, "customer");
  const moves = allowedMoves(offer.allowed_actions, "customer");
  const productName = offerProductName(offer.product.name);

  async function submit(values: OfferMoveValues) {
    if (!move || inFlight.current) return;
    inFlight.current = true;
    const request: CustomerOfferAnswer =
      move === "counter"
        ? { move, amountCents: values.amountCents ?? 0, message: values.text }
        : move === "accept"
          ? { move, expectedAmountCents: offer.current_amount.amount_cents }
          : { move: "withdraw", reason: values.text };
    try {
      await answer.mutateAsync(request);
      setSuccess(SUCCESS[move] ?? null);
      setFailure(null);
      setMove(null);
    } catch (error) {
      const outcome = describeOfferError(error, "answer");
      if (outcome.refetchAuth) void queryClient.invalidateQueries({ queryKey: AUTH_SESSION_QUERY_KEY });
      if (outcome.refetchOffer) {
        // The offer moved on: the dialog's move may no longer exist, so close
        // it and show the refusal next to the refreshed state.
        void queryClient.invalidateQueries({ queryKey: offerKeys.root });
        setFailure(outcome);
        setMove(null);
      } else {
        setFailure(outcome);
      }
    } finally {
      inFlight.current = false;
    }
  }

  const dialogOpen = move !== null;

  return (
    <div className="flex min-w-0 flex-col">
      <div>
        <AccountBackLink href="/account/offers">Your offers</AccountBackLink>
      </div>
      <PageHeader
        eyebrow="Offer details"
        title={`Offer on ${productName}`}
        meta={<StatusBadge label={status.label} tone={status.tone} />}
        actions={
          offer.product.slug ? (
            <Link href={`/shop/${encodeURIComponent(offer.product.slug)}`} className={buttonLinkClassName("outline")}>
              View product
            </Link>
          ) : undefined
        }
      />

      <div className="flex min-w-0 flex-col gap-6">
        {success && (
          <p
            role="status"
            className="flex items-start gap-3 rounded-card border border-primary/20 bg-secondary-container/40 p-4 text-body-md text-on-surface"
          >
            <Icon name="check-circle" className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
            <span className="min-w-0">{success}</span>
          </p>
        )}
        {failure && !dialogOpen && <Alert variant="error" message={failure.message} />}

        <AccountSection title="Offer details" icon="sell">
          <OfferFacts offer={offer} perspective="customer" />
        </AccountSection>

        {moves.length > 0 && (
          <AccountSection title="Your reply">
            <div className="flex flex-col gap-3 tablet:flex-row tablet:flex-wrap">
              {moves.map((item, index) => (
                <Button
                  key={item}
                  type="button"
                  variant={item === "withdraw" ? "outline" : index === 0 ? "primary" : "secondary"}
                  onClick={() => {
                    answer.reset();
                    setFailure(null);
                    setSuccess(null);
                    setMove(item);
                  }}
                >
                  {MOVE_LABELS[item]}
                </Button>
              ))}
            </div>
          </AccountSection>
        )}

        {offer.status === "accepted" && <OfferCheckoutPanel offer={offer} />}
        {offer.status === "paid" && (
          <p className="flex items-start gap-3 rounded-card border border-info-outline bg-info-container p-4 text-body-md text-on-info-container">
            <Icon name="mail" className="mt-0.5 h-5 w-5 shrink-0 text-info" />
            <span className="min-w-0">
              This offer has been paid. Your STL file is delivered by email; see{" "}
              <Link href="/account/orders" className="font-semibold underline">
                your orders
              </Link>{" "}
              for the order.
            </span>
          </p>
        )}

        <OfferHistory rounds={offer.rounds} perspective="customer" />
      </div>

      <OfferMoveDialog
        move={move}
        perspective="customer"
        currentAmount={offer.current_amount}
        pending={answer.isPending}
        error={dialogOpen && failure ? failure.message : null}
        fieldError={dialogOpen ? (failure?.field ?? null) : null}
        onSubmit={(values) => void submit(values)}
        onClose={() => {
          setMove(null);
          setFailure(null);
        }}
      />
    </div>
  );
}

export function OfferNotFound() {
  return (
    <>
      <PageHeader eyebrow="Offer details" title="Offer not found" />
      <div className={ACCOUNT_CARD}>
        <EmptyState
          icon="sell"
          message="We couldn't find this offer in your account. Check the link, or find it in your offers."
          actionLabel="View your offers"
          actionHref="/account/offers"
        />
      </div>
    </>
  );
}
