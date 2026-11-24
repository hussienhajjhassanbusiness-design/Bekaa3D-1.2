"use client";

import { AdminBackLink, AdminField as Field, AdminSection } from "@/components/admin/adminUi";
import Link from "next/link";
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { Alert } from "@/components/feedback/Alert";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { NotFoundContent } from "@/components/feedback/NotFoundContent";
import { Button } from "@/components/forms/Button";
import { OfferFacts } from "@/components/offers/OfferFacts";
import { OfferHistory } from "@/components/offers/OfferHistory";
import { OfferMoveDialog, type OfferMoveValues } from "@/components/offers/OfferMoveDialog";
import { describeAdminError } from "@/lib/admin/adminErrorMessages";
import { isMfaRequiredError } from "@/lib/admin/adminRequest";
import { adminOfferKeys, offersAdminApi } from "@/lib/admin/offers/offersAdminApi";
import type { ApiError } from "@/lib/api/ApiError";
import { describeOfferError, type OfferErrorOutcome } from "@/lib/offers/offerErrors";
import { allowedMoves, describeOfferStatus, formatMoney, offerProductName } from "@/lib/offers/offerModel";
import type { AdminOfferDetailReadDTO, OfferMove } from "@/lib/offers/offerTypes";
import { isOrderId } from "@/lib/orders/orderModel";
import { productsApi, productsKeys } from "@/lib/catalog/productsApi";
import type { ProductDetail } from "@/lib/catalog/productTypes";

const MOVE_LABELS: Record<OfferMove, string> = {
  accept: "Accept offer",
  counter: "Counter-offer",
  reject: "Reject offer",
  withdraw: "Withdraw",
};

const SUCCESS: Partial<Record<OfferMove, string>> = {
  accept: "Offer accepted. The customer's checkout window is open.",
  counter: "Counter-offer sent. It's now the customer's turn.",
  reject: "Offer rejected.",
};

type AdminAnswer =
  | { move: "accept"; expectedAmountCents: number }
  | { move: "counter"; amountCents: number; message?: string }
  | { move: "reject"; reason?: string };

// #FVS-OFFERS-ADMIN-DETAIL (phase 6C) — /admin/offers/[id]
// (GET /api/v1/admin/offers/{id}). The buttons are exactly the server's
// `allowed_actions` (accept / counter / reject, only on the
// administrator's turn). Each answer goes through a confirmation, carries
// X-CSRF-Token, has a synchronous in-flight guard and is never retried.
// Customer text is rendered as plain React text.
export function AdminOfferView({ offerId }: { offerId: string }) {
  const validId = isOrderId(offerId);
  const queryClient = useQueryClient();
  const detail = useQuery<AdminOfferDetailReadDTO, ApiError>({
    queryKey: adminOfferKeys.detail(offerId),
    queryFn: () => offersAdminApi.getOffer(offerId),
    enabled: validId,
  });
  const answer = useMutation({
    mutationFn: (request: AdminAnswer) => {
      switch (request.move) {
        case "accept":
          return offersAdminApi.acceptOffer(offerId, request.expectedAmountCents);
        case "counter":
          return offersAdminApi.counterOffer(offerId, request.amountCents, request.message);
        case "reject":
          return offersAdminApi.rejectOffer(offerId, request.reason);
      }
    },
    retry: false,
  });
  // Today's price, from the server's public product read: the price the shop
  // charges now, which is also the backend's offer ceiling — the promotional
  // price while a promotion applies (backend docs/promotions.md). The offer's
  // own product summary carries no price. Display and hint only: Accept/
  // Counter are still capped by the backend. A failed read (e.g. a hidden
  // product, where counter/accept are not offered anyway) leaves it out.
  const productSlug = detail.data?.product.slug;
  const product = useQuery<ProductDetail, ApiError>({
    queryKey: productsKeys.detail(productSlug ?? ""),
    queryFn: () => productsApi.getProductBySlug(productSlug ?? ""),
    enabled: productSlug !== undefined,
    retry: false,
  });
  const listPrice = product.data?.price ?? null;
  const productPromotion = product.data?.promotion ?? null;
  const inFlight = useRef(false);
  const [move, setMove] = useState<OfferMove | null>(null);
  const [failure, setFailure] = useState<OfferErrorOutcome | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  if (!validId) return <NotFoundContent />;
  if (detail.isLoading) return <LoadingSpinner />;
  if (detail.isError) {
    return detail.error.kind === "http" && (detail.error.status === 404 || detail.error.status === 422) ? (
      <NotFoundContent />
    ) : (
      <Alert variant="error" message={describeAdminError(detail.error)} />
    );
  }
  const offer = detail.data;
  if (!offer) return <NotFoundContent />;

  const status = describeOfferStatus(offer.status, "admin");
  const moves = allowedMoves(offer.allowed_actions, "admin");

  async function submit(values: OfferMoveValues) {
    if (!move || inFlight.current || !offer) return;
    inFlight.current = true;
    const request: AdminAnswer =
      move === "accept"
        ? { move, expectedAmountCents: offer.current_amount.amount_cents }
        : move === "counter"
          ? { move, amountCents: values.amountCents ?? 0, message: values.text }
          : { move: "reject", reason: values.text };
    try {
      const updated = await answer.mutateAsync(request);
      queryClient.setQueryData(adminOfferKeys.detail(offerId), updated);
      void queryClient.invalidateQueries({ queryKey: adminOfferKeys.lists() });
      setSuccess(SUCCESS[move] ?? null);
      setFailure(null);
      setMove(null);
    } catch (error) {
      if (isMfaRequiredError(error)) {
        setFailure({
          kind: "message",
          message: describeAdminError(error),
          refetchOffer: false,
          refetchProduct: false,
          refetchAuth: false,
        });
        return;
      }
      const outcome = describeOfferError(error, "answer");
      setFailure(outcome);
      if (outcome.refetchOffer) {
        void queryClient.invalidateQueries({ queryKey: adminOfferKeys.root });
        setMove(null);
      }
    } finally {
      inFlight.current = false;
    }
  }

  const dialogOpen = move !== null;

  return (
    <div className="flex min-w-0 flex-col gap-6 break-words">
      <div>
        <AdminBackLink href="/admin/offers">Offers</AdminBackLink>
      </div>
      <div className="flex flex-col gap-2">
        <h1 className="break-words font-headline text-headline-lg text-on-surface">
          Offer on {offerProductName(offer.product.name)}
        </h1>
        <div>
          <StatusBadge label={status.label} tone={status.tone} />
        </div>
      </div>

      {success && (
        <p
          role="status"
          className="rounded-card border border-primary/20 border-l-4 border-l-primary bg-surface-container-low p-4 font-body text-body-md text-on-surface"
        >
          {success}
        </p>
      )}
      {failure && !dialogOpen && <Alert variant="error" message={failure.message} />}

      <AdminSection title="Offer details">
        <OfferFacts offer={offer} perspective="admin">
          <Field label="Customer">
            {offer.customer.email ?? "Unknown customer"}
            {" · "}
            <Link
              href={`/admin/customers/${encodeURIComponent(offer.customer.id)}`}
              className="font-semibold text-primary underline underline-offset-2 hover:text-primary-container"
            >
              View customer
            </Link>
          </Field>
          <Field label="Product">
            <Link
              href={`/admin/products/${encodeURIComponent(offer.product.id)}`}
              className="font-semibold text-primary underline underline-offset-2 hover:text-primary-container"
            >
              {offerProductName(offer.product.name)}
            </Link>
          </Field>
          {listPrice && (
            <Field label="Price today">
              {formatMoney(listPrice)}
              {productPromotion && product.data && (
                <span className="text-on-surface-variant">
                  {" "}
                  ({productPromotion.name}; list price {formatMoney(product.data.list_price)})
                </span>
              )}
            </Field>
          )}
        </OfferFacts>
      </AdminSection>

      {moves.length > 0 ? (
        <section
          aria-labelledby="admin-offer-actions"
          className="flex flex-col gap-3 rounded-card border border-outline-variant/40 bg-surface-container-lowest p-5 shadow-sm tablet:p-6"
        >
          <h2 id="admin-offer-actions" className="font-headline text-headline-md text-on-surface">
            Your reply
          </h2>
          <p className="text-xs text-on-surface-variant">Each reply is final and can&apos;t be undone.</p>
          <div className="flex flex-wrap gap-2">
            {moves.map((item) => (
              <Button
                key={item}
                type="button"
                variant={item === "accept" ? "primary" : item === "reject" ? "destructive" : "secondary"}
                onClick={() => {
                  answer.reset();
                  setFailure(null);
                  setSuccess(null);
                  setMove(item);
                }}
              >
                {item === "accept" ? `Accept ${formatMoney(offer.current_amount)}` : MOVE_LABELS[item]}
              </Button>
            ))}
          </div>
        </section>
      ) : (
        offer.status === "awaiting_customer" && (
          <p className="text-body-md text-on-surface-variant">Waiting for the customer to reply.</p>
        )
      )}

      <OfferHistory rounds={offer.rounds} perspective="admin" />

      <OfferMoveDialog
        move={move}
        perspective="admin"
        currentAmount={offer.current_amount}
        listPrice={listPrice}
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
