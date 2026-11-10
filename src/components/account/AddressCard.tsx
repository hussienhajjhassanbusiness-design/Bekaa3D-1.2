import { useId } from "react";
import { Button } from "@/components/forms/Button";
import { StatusBadge } from "@/components/admin/StatusBadge";
import type { AddressModel } from "@/lib/addresses/addressModel";

export interface AddressCardProps {
  address: AddressModel;
  onEdit: (addressId: string) => void;
  // A request only — the container confirms before anything is deleted.
  onDelete: (addressId: string) => void;
  onSetDefault: (addressId: string) => void;
  isSettingDefault?: boolean;
  actionsDisabled?: boolean;
}

// #FVS023-ADDRESS-CARD
//
// Presentational only — no network. One saved address from the real
// AddressRead. "Default" is visible text, never colour alone. Action
// buttons carry the label in their accessible name ("Edit Home") so
// screen-reader users can tell several cards' buttons apart; the visible
// text stays first in the name (WCAG 2.5.3 label-in-name).
// #ARCHITECTURE-ADDRESS-NO-ZONE-INFERENCE — no zone/rate/fee, ever.
export function AddressCard({
  address,
  onEdit,
  onDelete,
  onSetDefault,
  isSettingDefault = false,
  actionsDisabled = false,
}: AddressCardProps) {
  const headingId = useId();

  return (
    <article
      aria-labelledby={headingId}
      className="flex h-full flex-col gap-3 rounded-md border border-border-default bg-white p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h2 id={headingId} className="break-words text-h4 font-semibold text-text-primary">
          {address.label}
        </h2>
        {address.isDefault && <StatusBadge label="Default" tone="positive" />}
      </div>

      <div className="flex-1 break-words">
        {address.displayLines.map((line, index) => (
          <p key={index} className="text-body text-text-primary">
            {line}
          </p>
        ))}
        <p className="mt-2 whitespace-pre-line text-caption text-text-secondary">{address.landmarkNotes}</p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="secondary"
          aria-label={`Edit ${address.label}`}
          disabled={actionsDisabled}
          onClick={() => onEdit(address.id)}
        >
          Edit
        </Button>
        {!address.isDefault && (
          <Button
            type="button"
            variant="secondary"
            aria-label={`Set as default: ${address.label}`}
            disabled={actionsDisabled}
            isLoading={isSettingDefault}
            onClick={() => onSetDefault(address.id)}
          >
            Set as default
          </Button>
        )}
        <Button
          type="button"
          variant="secondary"
          aria-label={`Delete ${address.label}`}
          disabled={actionsDisabled}
          onClick={() => onDelete(address.id)}
        >
          Delete
        </Button>
      </div>
    </article>
  );
}
