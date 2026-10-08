"use client";

import { useState } from "react";
import { Button } from "@/components/forms/Button";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import type { TransitionAffordance } from "@/lib/admin/adminOrderModel";

export interface TransitionActionsProps {
  actions: readonly TransitionAffordance[];
  pendingActionId?: string | null;
  onSelectAction: (actionId: string) => void;
}

// #SECURITY-SERVER-FULFILLMENT-STATE-MACHINE
//
// Renders exactly the supplied legal actions — zero actions renders
// nothing, never a locally-invented "Next" fallback. An action
// requiring confirmation reuses the existing ConfirmDialog (no second
// focus-trap); one that doesn't fires immediately. All buttons
// disable while any action is pending — this component never
// optimistically assumes a transition succeeded (it has no status
// field to mutate at all).
export function TransitionActions({ actions, pendingActionId = null, onSelectAction }: TransitionActionsProps) {
  const [confirmingAction, setConfirmingAction] = useState<TransitionAffordance | null>(null);
  const isPending = pendingActionId !== null;

  function handleClick(action: TransitionAffordance) {
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
