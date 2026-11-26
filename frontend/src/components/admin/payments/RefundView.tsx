"use client";

import { AdminBackLink, AdminRow as Row } from "@/components/admin/adminUi";
import Link from "next/link";
import { useState } from "react";
import { AdminActionDialog } from "@/components/admin/orders/AdminActionDialog";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { Button } from "@/components/forms/Button";
import { TextAreaField } from "@/components/forms/TextAreaField";
import { TextField } from "@/components/forms/TextField";
import {
  describeAdminRefundKind,
  describeAdminRefundStatus,
  describePaymentProvider,
} from "@/lib/admin/orders/adminOrderPresentation";
import { adminPaymentsApi } from "@/lib/admin/payments/adminPaymentsApi";
import {
  REFUND_TEXT_MAX,
  refundActions,
  SETTLEMENT_REFERENCE_MAX,
  type RefundAction,
} from "@/lib/admin/payments/adminPaymentPresentation";
import type { RefundDetailDTO } from "@/lib/admin/payments/adminPaymentTypes";
import { useRefundAttemptTracker } from "@/lib/admin/payments/refundIdempotency";
import { useAdminFinancialWrite } from "@/lib/admin/payments/useAdminPayments";
import { formatOrderDateTime } from "@/lib/orders/orderFormat";

// #FVS028-REFUND-VIEW (phase 5I)
//
// GET /api/v1/admin/refunds/{id} and its transitions. The money moves in the
// provider's dashboard (or by hand for cash), never here (ADR-024 d16):
//   pending           -> Mark settled {reference?, note?} | Mark failed {reason} | Void {reason}
//   failed, still owed -> Reissue (Idempotency-Key, a new pending refund) | Void
//   settled / voided / reissued -> nothing.
// Offered on the documented state machine; every action confirmed; the
// server re-checks and its 409 is shown.
export function RefundView({ refund }: { refund: RefundDetailDTO }) {
  const status = describeAdminRefundStatus(refund.status);
  return (
    <article aria-labelledby="refund-heading" className="flex min-w-0 flex-col gap-6 break-words">
      <header className="flex flex-col gap-2">
        <div>
          <AdminBackLink href="/admin/refunds">Back to refunds</AdminBackLink>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <h1 id="refund-heading" className="break-words font-headline text-headline-lg text-on-surface">
            {describeAdminRefundKind(refund.kind)} for order {refund.order_number}
          </h1>
          <StatusBadge label={status.label} tone={status.tone} />
          {refund.owed && <StatusBadge label="Still owed" tone="warning" />}
        </div>
      </header>

      <RefundActions refund={refund} />

      <section
        aria-label="Refund"
        className="flex flex-col gap-3 rounded-card border border-outline-variant/40 bg-surface-container-lowest p-5 shadow-sm tablet:p-6"
      >
        <h2 className="font-headline text-headline-md text-on-surface">Refund</h2>
        <dl className="flex flex-col gap-2 text-body-md">
          <Row label="Amount">
            <PriceDisplay amountCents={refund.amount_cents} currency={refund.currency} />
          </Row>
          <Row label="Order">
            <Link
              href={`/admin/orders/${refund.order_id}`}
              className="font-semibold text-primary underline underline-offset-2 hover:text-primary-container"
            >
              {refund.order_number}
            </Link>
          </Row>
          <Row label="Paid through">{describePaymentProvider(refund.payment_provider)}</Row>
          <Row label="Recorded">{formatOrderDateTime(refund.created_at)}</Row>
          <Row label="Reason">
            <span className="whitespace-pre-line">{refund.reason}</span>
          </Row>
          {refund.settled_at && <Row label="Settled">{formatOrderDateTime(refund.settled_at)}</Row>}
          {refund.settlement_reference && <Row label="Settlement reference">{refund.settlement_reference}</Row>}
          {refund.settlement_note && <Row label="Settlement note">{refund.settlement_note}</Row>}
          {refund.failed_at && <Row label="Failed">{formatOrderDateTime(refund.failed_at)}</Row>}
          {refund.failure_reason && <Row label="Failure reason">{refund.failure_reason}</Row>}
          {refund.voided_at && <Row label="Voided">{formatOrderDateTime(refund.voided_at)}</Row>}
          {refund.void_reason && <Row label="Void reason">{refund.void_reason}</Row>}
          {refund.reissue_of_refund_id && (
            <Row label="Reissue of">
              <Link
                href={`/admin/refunds/${refund.reissue_of_refund_id}`}
                className="font-semibold text-primary underline underline-offset-2 hover:text-primary-container"
              >
                Earlier refund
              </Link>
            </Row>
          )}
          {refund.reissued_by_refund_id && (
            <Row label="Reissued as">
              <Link
                href={`/admin/refunds/${refund.reissued_by_refund_id}`}
                className="font-semibold text-primary underline underline-offset-2 hover:text-primary-container"
              >
                New refund
              </Link>
            </Row>
          )}
        </dl>
        {refund.items.length > 0 && (
          <ul className="flex flex-col gap-1 border-t border-outline-variant/40 pt-2">
            {refund.items.map((item) => (
              <li key={item.order_item_id} className="flex justify-between gap-2 text-body-md">
                <span>{item.product_name}</span>
                <PriceDisplay amountCents={item.amount_cents} currency={refund.currency} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </article>
  );
}

const ACTION_COPY: Record<RefundAction, { button: string; title: string; description: string; destructive?: boolean }> =
  {
    settle: {
      button: "Mark settled",
      title: "Mark this refund settled?",
      description: "Only after the money was returned (provider dashboard, or cash handed back).",
    },
    fail: {
      button: "Mark failed",
      title: "Mark this refund failed?",
      description: "It stays owed until it is reissued or voided.",
      destructive: true,
    },
    void: {
      button: "Void refund",
      title: "Void this refund?",
      description: "Closes a refund recorded by mistake, unpaid. Never after settlement.",
      destructive: true,
    },
    reissue: {
      button: "Reissue refund",
      title: "Reissue this refund?",
      description: "Creates a new pending refund with the same items and amount.",
    },
  };

function RefundActions({ refund }: { refund: RefundDetailDTO }) {
  const write = useAdminFinancialWrite();
  const tracker = useRefundAttemptTracker();
  const [open, setOpen] = useState<RefundAction | null>(null);
  const [reference, setReference] = useState("");
  const [text, setText] = useState("");
  const [fieldError, setFieldError] = useState<string | undefined>(undefined);
  const actions = refundActions(refund);
  if (actions.length === 0 && open === null) return null;

  function start(action: RefundAction) {
    write.reset();
    setReference("");
    setText("");
    setFieldError(undefined);
    setOpen(action);
  }

  async function confirm() {
    if (!open) return;
    let call: () => Promise<RefundDetailDTO>;
    if (open === "settle") {
      const body = {
        ...(reference.trim() ? { reference: reference.trim() } : {}),
        ...(text.trim() ? { note: text.trim() } : {}),
      };
      call = () => adminPaymentsApi.settleRefund(refund.id, body);
    } else if (open === "reissue") {
      const key = tracker.keyFor(`reissue:${refund.id}`);
      call = () => adminPaymentsApi.reissueRefund(refund.id, key);
    } else {
      if (!text.trim()) {
        setFieldError("Enter a reason.");
        return;
      }
      const body = { reason: text.trim() };
      call =
        open === "fail"
          ? () => adminPaymentsApi.failRefund(refund.id, body)
          : () => adminPaymentsApi.voidRefund(refund.id, body);
    }
    if (await write.run(call, open === "reissue" ? tracker : undefined)) setOpen(null);
  }

  const copy = open ? ACTION_COPY[open] : null;
  return (
    <section
      aria-label="Refund actions"
      className="flex flex-col gap-3 rounded-card border border-error/30 border-t-4 border-t-error bg-surface-container-lowest p-5 shadow-sm tablet:p-6"
    >
      <h2 className="font-headline text-headline-md text-on-surface">Refund actions</h2>
      <div className="flex flex-wrap gap-2">
        {actions.map((a) => (
          <Button
            key={a}
            type="button"
            variant={ACTION_COPY[a].destructive ? "secondary" : "primary"}
            onClick={() => start(a)}
          >
            {ACTION_COPY[a].button}
          </Button>
        ))}
      </div>
      <AdminActionDialog
        open={open !== null}
        title={copy?.title ?? ""}
        description={
          <p>
            {copy?.description} Amount: <PriceDisplay amountCents={refund.amount_cents} currency={refund.currency} />.
          </p>
        }
        confirmLabel={copy?.button ?? ""}
        destructive={copy?.destructive}
        pending={write.state.kind === "pending"}
        error={write.state.kind === "error" ? write.state.message : null}
        onConfirm={() => void confirm()}
        onClose={() => setOpen(null)}
      >
        {open === "settle" && (
          <>
            <TextField
              label="Settlement reference (optional)"
              value={reference}
              maxLength={SETTLEMENT_REFERENCE_MAX}
              onChange={(e) => setReference(e.target.value)}
            />
            <TextAreaField
              label="Note (optional)"
              rows={2}
              maxLength={REFUND_TEXT_MAX}
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </>
        )}
        {(open === "fail" || open === "void") && (
          <TextAreaField
            label="Reason"
            rows={3}
            maxLength={REFUND_TEXT_MAX}
            value={text}
            onChange={(e) => setText(e.target.value)}
            error={fieldError}
          />
        )}
      </AdminActionDialog>
    </section>
  );
}
