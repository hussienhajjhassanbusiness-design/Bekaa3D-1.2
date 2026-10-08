"use client";

import { useState } from "react";
import { Button } from "@/components/forms/Button";
import { ConfirmDialog } from "./ConfirmDialog";
import type { OrderActionAffordance } from "@/lib/orders/orderActionModel";

export interface OrderActionButtonsProps {
  actions: readonly OrderActionAffordance[];
  pendingActionId?: string | null;
  onSelectAction: (actionId: string) => void;
}

// #ARCHITECTURE-SERVER-PROVIDED-ORDER-ACTIONS
//
// Extracted from FVS-030's TransitionActions (FVS-031-IMPLEMENTATION-
// PLAN.md §1) — admin/TransitionActions.tsx now wraps this unchanged,
// and customer-side CancelOrderLineButton composes it directly, so
// both consume one rendering primitive rather than two parallel
// ones. Renders exactly the supplied legal actions — zero actions
// renders nothing, never a locally-invented "Next" fallback. An
// action requiring confirmation reuses the existing ConfirmDialog (no
// second focus trap); one that doesn't fires immediately. All
// buttons disable while any action is pending — this component never
// optimistically assumes a transition succeeded (it has no status
// field to mutate at all).
export function OrderActionButtons({ actions, pendingActionId = null, onSelectAction }: OrderActionButtonsProps) {
  const [confirmingAction, setConfirmingAction] = useState<OrderActionAffordance | null>(null);
  const isPending = pendingActionId !== null;

  function handleClick(action: OrderActionAffordance) {
    if (action.requiresConfirmation) {
      setConfirmingAction(action);
    } else {
      onSelectAction(action.id);
    }
  }

  return (
    <>
      <div className="flex flex-wrap gap-2">
        {actions.map((action) => (
          <Button key={action.id} type="button" onClick={() => handleClick(action)} disabled={isPending}>
            {action.label}
          </Button>
        ))}
      </div>

      <ConfirmDialog
        open={confirmingAction !== null}
        title={confirmingAction?.label ?? ""}
        description={`Confirm: ${confirmingAction?.label ?? ""}`}
        onConfirm={() => {
          if (confirmingAction) {
            onSelectAction(confirmingAction.id);
          }
          setConfirmingAction(null);
        }}
        onCancel={() => setConfirmingAction(null)}
      />
    </>
  );
}
