import { Button } from "@/components/forms/Button";
import { StatusBadge } from "@/components/admin/StatusBadge";
import type { AddressModel } from "@/lib/addresses/addressModel";

export interface AddressCardProps {
  address: AddressModel;
  // Always present — the click signals "the user wants to delete this
  // card"; a caller (AddressList) decides what that means (e.g. open a
  // confirmation dialog first). No real network call happens here.
  onDelete: (addressId: string) => void;
  // Seam only: no AddressForm exists yet this batch (field matrix
  // unconfirmed, plan §6) — no caller supplies this, so no dead Edit
  // button renders.
  onEdit?: (addressId: string) => void;
}

// #FVS023-ADDRESS-CARD
//
// Presentational only — no network, no query. Renders only
// `displayLines` (pre-formatted text; no individual address field is
// claimed) and a visible "Default" text badge, never color alone
// (#ARCHITECTURE-ADDRESS-ADAPTER). Never renders shipping-zone/rate
// information — address management and zone selection are different
// concerns (#ARCHITECTURE-ADDRESS-NO-ZONE-INFERENCE).
export function AddressCard({ address, onDelete, onEdit }: AddressCardProps) {
  return (
    <div className="flex flex-col gap-2 rounded-md border border-border-default p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          {address.displayLines.map((line, index) => (
            <p key={index} className="text-body text-text-primary">
              {line}
            </p>
          ))}
        </div>
        {address.isDefault && <StatusBadge label="Default" tone="positive" />}
      </div>
      <div className="flex items-center gap-2">
        {onEdit && (
          <Button type="button" onClick={() => onEdit(address.id)}>
            Edit
          </Button>
        )}
        <Button type="button" onClick={() => onDelete(address.id)}>
          Delete
        </Button>
      </div>
    </div>
  );
}
