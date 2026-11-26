"use client";

import { useState } from "react";
import { AdminActionDialog } from "@/components/admin/orders/AdminActionDialog";
import { MoneyInput } from "@/components/forms/MoneyInput";
import { TextAreaField } from "@/components/forms/TextAreaField";
import { formatMoney, type OfferPerspective } from "@/lib/offers/offerModel";
import { MAX_OFFER_MESSAGE, OFFER_CURRENCY, type OfferMove } from "@/lib/offers/offerTypes";
import type { PriceRead } from "@/lib/catalog/productTypes";

export interface OfferMoveValues {
  amountCents?: number;
  text?: string;
}

export interface OfferMoveDialogProps {
  move: OfferMove | null;
  perspective: OfferPerspective;
  currentAmount: PriceRead;
  // Today's price (the offer ceiling), when the caller has it from the server
  // (the admin page reads the public product's `price`, promotional while a
  // promotion applies). Shown as a hint on the counter amount only; the
  // backend's own 422 stays the authority.
  listPrice?: PriceRead | null;
  pending: boolean;
  // Frontend-owned copy for a server refusal; the dialog stays open with it.
  error: string | null;
  fieldError?: { name: "amount" | "message"; message: string } | null;
  onSubmit: (values: OfferMoveValues) => void;
  onClose: () => void;
}

const TITLES: Record<OfferMove, string> = {
  accept: "Accept this amount?",
  counter: "Make a counter-offer",
  reject: "Reject this offer?",
  withdraw: "Withdraw your offer?",
};

const CONFIRM: Record<OfferMove, string> = {
  accept: "Accept",
  counter: "Send counter-offer",
  reject: "Reject offer",
  withdraw: "Withdraw offer",
};

function description(move: OfferMove, perspective: OfferPerspective, amount: string): string {
  switch (move) {
    case "accept":
      return perspective === "customer"
        ? `You agree to buy this STL for ${amount}. A checkout window opens; pay within it to keep this price.`
        : `The customer's ${amount} is accepted (or today's list price, if that is lower). They then have a limited window to check out.`;
    case "counter":
      return perspective === "customer"
        ? `The amount on the table is ${amount}. Propose a different amount; it's then our turn to reply.`
        : `The customer offered ${amount}. Propose an amount up to today's list price; it's then the customer's turn.`;
    case "reject":
      return "The negotiation ends and can't be reopened. The customer may have to wait before making another offer on this product.";
    case "withdraw":
      return "The negotiation ends and can't be reopened. You can make a new offer on this product later.";
  }
}

// #FVS-OFFERS-MOVE-DIALOG (phase 6C)
//
// The one confirmation every offer answer goes through, for the customer
// (accept / counter / withdraw) and the administrator (accept / counter /
// reject). Built on the shared AdminActionDialog (DialogShell: focus trap,
// Escape, focus return). Accept sends no amount of its own: the caller
// passes `current_amount` as `expected_amount_cents`, so a stale page is
// refused rather than binding an amount the caller never saw.
export function OfferMoveDialog(props: OfferMoveDialogProps) {
  // Remount per move so a previous draft never leaks into the next dialog.
  return <OfferMoveDialogInner key={props.move ?? "closed"} {...props} />;
}

function OfferMoveDialogInner({
  move,
  perspective,
  currentAmount,
  listPrice,
  pending,
  error,
  fieldError,
  onSubmit,
  onClose,
}: OfferMoveDialogProps) {
  const [amountCents, setAmountCents] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  const amount = formatMoney(currentAmount);
  const needsAmount = move === "counter";
  const needsText = move === "counter" || move === "reject" || move === "withdraw";

  function submit() {
    if (!move) return;
    if (needsAmount && (amountCents === null || amountCents < 1)) {
      setLocalError("Enter an amount of at least $0.01.");
      return;
    }
    setLocalError(null);
    onSubmit({ amountCents: needsAmount ? (amountCents ?? undefined) : undefined, text: needsText ? text : undefined });
  }

  const amountError = localError ?? (fieldError?.name === "amount" ? fieldError.message : undefined);
  const textLabel =
    move === "counter"
      ? "Message (optional)"
      : perspective === "customer"
        ? "Reason (optional)"
        : "Reason for the customer (optional)";

  return (
    <AdminActionDialog
      open={move !== null}
      title={move ? TITLES[move] : ""}
      description={move ? <p>{description(move, perspective, amount)}</p> : null}
      confirmLabel={move ? CONFIRM[move] : "Confirm"}
      destructive={move === "reject" || move === "withdraw"}
      pending={pending}
      error={error}
      onConfirm={submit}
      onClose={onClose}
    >
      {needsAmount && (
        <MoneyInput
          label="Your counter-offer"
          hint={listPrice ? `Up to today's price, ${formatMoney(listPrice)}.` : undefined}
          currencyLabel={OFFER_CURRENCY}
          valueCents={amountCents}
          onChangeCents={(next) => {
            setAmountCents(next);
            setLocalError(null);
          }}
          error={amountError ?? undefined}
        />
      )}
      {needsText && (
        <TextAreaField
          label={textLabel}
          maxLength={MAX_OFFER_MESSAGE}
          value={text}
          onChange={(event) => setText(event.target.value)}
          error={fieldError?.name === "message" ? fieldError.message : undefined}
          disabled={pending}
        />
      )}
    </AdminActionDialog>
  );
}
