"use client";

import { useState } from "react";
import { Button } from "@/components/forms/Button";
import { AdminOrderLineItem } from "./AdminOrderLineItem";
import { TransitionActions } from "./TransitionActions";
import { AdminCancelDialog } from "./AdminCancelDialog";
import type { AdminOrderLineModel } from "@/lib/admin/adminOrderModel";

export interface AdminOrderLineProps {
  line: AdminOrderLineModel;
  pendingActionId?: string | null;
  onSelectAction: (lineId: string, actionId: string) => void;
  onAdminCancel?: (lineId: string, reason: string) => void;
  isCancellingLine?: boolean;
}

// #ARCHITECTURE-CUSTOMER-ADMIN-ORDER-BOUNDARY
//
// Composes FVS-029's AdminOrderLineItem completely unmodified (rendering
// `line` directly, since AdminOrderLineModel is a superset) alongside
// TransitionActions rendered separately — never injecting admin state
// into AdminOrderLineItem itself. A digital/STL line's absence of
// transition controls comes naturally from an empty
// `availableActions` array, never a hardcoded product-type check.
//
// Admin cancellation (FVS-031) is additive: it owns its own
// AdminCancelDialog instance internally, exactly mirroring how
// TransitionActions owns its own ConfirmDialog — no second
// focus-trap implementation. It never folds into availableActions
// (#SECURITY-SERVER-CANCELLATION-AUTHORITY), since VS-025 confirms
// admin cancel is its own endpoint, distinct from the transition
// endpoint that array models.
export function AdminOrderLine({
  line,
  pendingActionId,
  onSelectAction,
  onAdminCancel,
  isCancellingLine = false,
}: AdminOrderLineProps) {
  const [isCancelDialogOpen, setIsCancelDialogOpen] = useState(false);

  return (
    <div className="flex flex-col gap-2 tablet:flex-row tablet:items-center tablet:justify-between">
      <AdminOrderLineItem line={line} />
      <div className="flex flex-wrap items-center gap-2">
        <TransitionActions
          actions={line.availableActions}
          pendingActionId={pendingActionId}
          onSelectAction={(actionId) => onSelectAction(line.id, actionId)}
        />
        {line.adminCancelAction && (
          <Button type="button" onClick={() => setIsCancelDialogOpen(true)}>
            {line.adminCancelAction.label}
          </Button>
        )}
      </div>

      <AdminCancelDialog
        open={isCancelDialogOpen}
        onClose={() => setIsCancelDialogOpen(false)}
        lineId={line.id}
        refundObligationMessage={line.refundObligationMessage}
        isCancelling={isCancellingLine}
        onConfirm={(lineId, reason) => {
          onAdminCancel?.(lineId, reason);
          setIsCancelDialogOpen(false);
        }}
      />
    </div>
  );
}
