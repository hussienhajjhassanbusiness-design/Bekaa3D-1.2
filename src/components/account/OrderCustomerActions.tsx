"use client";

import { useEffect, useRef, useState } from "react";
import { Alert } from "@/components/feedback/Alert";
import { Button } from "@/components/forms/Button";
import { orderActionAvailability } from "@/lib/orders/orderActions";
import { formatOrderDate } from "@/lib/orders/orderFormat";
import type { OrderDetailModel } from "@/lib/orders/orderModel";
import { useOrderAction, type OrderActionState } from "@/lib/orders/useOrderActions";
import { CancelOrderDialog } from "./CancelOrderDialog";
import { ReportProblemDialog } from "./ReportProblemDialog";

// #FVS031-CUSTOMER-ACTIONS (phase 5G)
//
// The order page's focused "Order actions" section: Cancel order, "I
// received my items" and Report a problem, each offered only while the
// server's current state makes it meaningful (orderActions.ts), and the
// server-recorded receipt / problem timestamps. Separate from the payment
// section (FVS-027), which it never touches.
//
// Every outcome is the server's: after a success the canonical detail
// holds the POST's own OrderDetailRead and is re-read, so status, amount
// due, refunds and the "Order updates" history change through the normal
// order model. Nothing is appended or marked locally; the success notice
// only says the request went through. Focus moves to that notice, since
// the control that triggered it may no longer be offered.
const SUCCESS = {
  cancel: "Your cancellation went through. The order below shows its updated status.",
  "confirm-receipt": "Thanks. We've recorded that you received your items.",
  "report-problem": "Your report was sent. Our team will reply by email.",
} as const;

type Notice = keyof typeof SUCCESS;

function errorMessage(state: OrderActionState): string | null {
  return state.kind === "error" ? state.outcome.message : null;
}

export function OrderCustomerActions({ order }: { order: OrderDetailModel }) {
  const cancel = useOrderAction(order.id, "cancel");
  const receipt = useOrderAction(order.id, "confirm-receipt");
  const report = useOrderAction(order.id, "report-problem");
  const [cancelOpen, setCancelOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  // Remounting the report dialog after a success clears its text.
  const [reportKey, setReportKey] = useState(0);
  const [notice, setNotice] = useState<Notice | null>(null);
  const noticeRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (notice) noticeRef.current?.focus();
  }, [notice]);

  const available = orderActionAvailability(order);
  const offersAny = available.canCancel || available.canConfirmReceipt || available.canReportProblem;
  const recordsAny = available.receiptConfirmedAt !== null || available.problemReportedAt !== null;
  const receiptError = errorMessage(receipt.state);
  // A refusal re-reads the order, which may then offer nothing: the open
  // dialog (with its error) and the receipt error stay until dismissed.
  const engaged = notice !== null || cancelOpen || reportOpen || receiptError !== null;
  if (!offersAny && !recordsAny && !engaged) {
    return null;
  }

  async function confirmCancel(reason: string) {
    if (await cancel.submit(reason)) {
      setCancelOpen(false);
      setNotice("cancel");
    }
  }

  async function confirmReceipt() {
    setNotice(null);
    if (await receipt.submit()) setNotice("confirm-receipt");
  }

  async function sendReport(message: string) {
    if (await report.submit(message)) {
      setReportOpen(false);
      setReportKey((key) => key + 1);
      setNotice("report-problem");
    }
  }

  return (
    <section aria-label="Order actions" className="flex flex-col gap-3 rounded-md border border-border-default bg-white p-4">
      <h2 className="text-h3 font-bold text-text-primary">Order actions</h2>

      {notice && (
        <div ref={noticeRef} tabIndex={-1} className="outline-none">
          <Alert variant="success" message={SUCCESS[notice]} />
        </div>
      )}

      {available.receiptConfirmedAt && (
        <p className="text-body text-text-primary">
          You confirmed you received your items on {formatOrderDate(available.receiptConfirmedAt)}.
        </p>
      )}
      {available.problemReportedAt && (
        <p className="text-body text-text-primary">
          You reported a problem on {formatOrderDate(available.problemReportedAt)}. Our team will reply by email.
        </p>
      )}

      {receiptError && <Alert variant="error" message={receiptError} />}

      {offersAny && (
        <div className="flex flex-col gap-2 tablet:flex-row tablet:flex-wrap">
          {available.canConfirmReceipt && (
            <Button type="button" onClick={() => void confirmReceipt()} isLoading={receipt.state.kind === "pending"}>
              I received my items
            </Button>
          )}
          {available.canReportProblem && (
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setNotice(null);
                setReportOpen(true);
              }}
            >
              Report a problem
            </Button>
          )}
          {available.canCancel && (
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setNotice(null);
                cancel.reset();
                setCancelOpen(true);
              }}
            >
              Cancel order
            </Button>
          )}
        </div>
      )}

      <CancelOrderDialog
        open={cancelOpen}
        order={order}
        pending={cancel.state.kind === "pending"}
        error={errorMessage(cancel.state)}
        onConfirm={(reason) => void confirmCancel(reason)}
        onClose={() => {
          setCancelOpen(false);
          cancel.reset();
        }}
      />
      <ReportProblemDialog
        key={reportKey}
        open={reportOpen}
        pending={report.state.kind === "pending"}
        error={errorMessage(report.state)}
        onSubmit={(message) => void sendReport(message)}
        onClose={() => setReportOpen(false)}
      />
    </section>
  );
}
