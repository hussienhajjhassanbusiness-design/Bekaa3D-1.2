"use client";

import { useState } from "react";
import { Button } from "@/components/forms/Button";
import { SelectField } from "@/components/forms/SelectField";
import { TextAreaField } from "@/components/forms/TextAreaField";
import { adminOrdersApi } from "@/lib/admin/orders/adminOrdersApi";
import {
  describeAdminLineStatus,
  describeCancelReason,
  describeTransitionAction,
} from "@/lib/admin/orders/adminOrderPresentation";
import type { AdminOrderLineReadDTO, AvailableActionReadDTO, CancelReason } from "@/lib/admin/orders/adminOrderTypes";
import { useAdminOrderWrite } from "@/lib/admin/orders/useAdminOrders";
import { AdminActionDialog } from "./AdminActionDialog";

const NOTE_MAX = 500;

// #FVS030-LINE-ACTIONS (phase 5H)
//
// One button per server-provided `available_actions` entry, nothing else
// (ADR-025): no locally assumed state machine, no "next" fallback. Each
// opens an explicit confirmation with an optional history note (<= 500);
// a cancel whose action lists `cancel_reasons` requires one of exactly
// those. STL lines get only "Mark STL emailed" (ADR-019: manual email, no
// upload or download).
export function LineActions({ orderId, line }: { orderId: string; line: AdminOrderLineReadDTO }) {
  const write = useAdminOrderWrite();
  const [action, setAction] = useState<AvailableActionReadDTO | null>(null);
  const [note, setNote] = useState("");
  const [reason, setReason] = useState<CancelReason | "">("");
  const [fieldError, setFieldError] = useState<string | null>(null);

  // A refusal re-reads the order; if the line then offers nothing, the open
  // dialog (and its error) stays until dismissed.
  if (line.available_actions.length === 0 && action === null) return null;

  function open(next: AvailableActionReadDTO) {
    write.reset();
    setFieldError(null);
    setNote("");
    setReason("");
    setAction(next);
  }

  async function confirm() {
    if (!action) return;
    if (action.cancel_reasons.length > 0 && reason === "") {
      setFieldError("Choose a cancel reason.");
      return;
    }
    if (note.length > NOTE_MAX) {
      setFieldError(`Keep the note to ${NOTE_MAX} characters or fewer.`);
      return;
    }
    const body = {
      target_status: action.target_status,
      ...(note.trim() ? { reason: note.trim() } : {}),
      ...(reason ? { cancel_reason: reason } : {}),
    };
    if (await write.run(() => adminOrdersApi.transitionLine(orderId, line.id, body))) {
      setAction(null);
    }
  }

  const label = action ? describeTransitionAction(action.target_status, line.product_type) : "";
  const cancelling = action?.target_status === "cancelled";

  return (
    <>
      <div className="flex flex-wrap gap-2">
        {line.available_actions.map((a) => (
          <Button
            key={a.target_status}
            type="button"
            variant={a.target_status === "cancelled" ? "secondary" : "primary"}
            onClick={() => open(a)}
          >
            {describeTransitionAction(a.target_status, line.product_type)}
          </Button>
        ))}
      </div>
      <AdminActionDialog
        open={action !== null}
        title={`${label}?`}
        description={
          <p>
            {line.name}: {describeAdminLineStatus(line.fulfillment_status, line.product_type).label} →{" "}
            {action ? describeAdminLineStatus(action.target_status, line.product_type).label : ""}.
            {cancelling ? " This can't be undone." : ""}
          </p>
        }
        confirmLabel={label}
        destructive={cancelling}
        pending={write.state.kind === "pending"}
        error={write.state.kind === "error" ? write.state.message : null}
        onConfirm={() => void confirm()}
        onClose={() => setAction(null)}
      >
        {action && action.cancel_reasons.length > 0 && (
          <SelectField
            label="Cancel reason"
            value={reason}
            onChange={(event) => {
              setReason(event.target.value as CancelReason | "");
              setFieldError(null);
            }}
            error={fieldError && reason === "" ? fieldError : undefined}
          >
            <option value="">Choose a reason</option>
            {action.cancel_reasons.map((r) => (
              <option key={r} value={r}>
                {describeCancelReason(r)}
              </option>
            ))}
          </SelectField>
        )}
        <TextAreaField
          label="Note for the order history (optional)"
          rows={2}
          value={note}
          maxLength={NOTE_MAX}
          onChange={(event) => setNote(event.target.value)}
          error={fieldError && note.length > NOTE_MAX ? fieldError : undefined}
        />
      </AdminActionDialog>
    </>
  );
}
