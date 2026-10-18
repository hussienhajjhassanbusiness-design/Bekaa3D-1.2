"use client";

import { useId } from "react";
import type { AddressModel } from "@/lib/addresses/addressModel";
import type { DeliveryMethodSelection } from "@/lib/checkout/checkoutModels";

export interface DeliveryMethodSelectorProps {
  addresses: readonly AddressModel[];
  selection: DeliveryMethodSelection | null;
  onSelect: (selection: DeliveryMethodSelection | null) => void;
  // Rendered only when explicitly true — pickup availability is
  // unconfirmed (FVS-026-IMPLEMENTATION-PLAN.md §0), so no caller
  // means no Pickup option, never an invented default.
  pickupAvailable?: boolean;
}

// #FVS026 — reuses FVS-023's AddressModel directly, no checkout-
// specific duplicate. ADR-024 removed shipping charges, so there is
// no shipping-zone step: choosing an address is itself a complete
// DeliveryMethodSelection, fired the moment it is clicked.
export function DeliveryMethodSelector({ addresses, selection, onSelect, pickupAvailable }: DeliveryMethodSelectorProps) {
  const groupName = useId();

  const isPickupSelected = selection?.kind === "pickup";
  const activeAddressId = selection?.kind === "address" ? selection.addressId : null;

  function handleChooseAddress(addressId: string) {
    onSelect({ kind: "address", addressId });
  }

  function handleChoosePickup() {
    onSelect({ kind: "pickup" });
  }

  return (
    <fieldset>
      <legend className="text-label font-semibold uppercase tracking-label text-text-primary">Delivery method</legend>
      <div className="mt-2 flex flex-col gap-3">
        {addresses.map((address) => {
          const label = address.displayLines.join(", ");
          const isActive = activeAddressId === address.id;
          return (
            <label key={address.id} className="flex items-center gap-2 text-body text-text-primary">
              <input
                type="radio"
                name={groupName}
                checked={isActive}
                onChange={() => handleChooseAddress(address.id)}
              />
              {label}
            </label>
          );
        })}

        {pickupAvailable && (
          <label className="flex items-center gap-2 text-body text-text-primary">
            <input type="radio" name={groupName} checked={isPickupSelected} onChange={handleChoosePickup} />
            Pickup
          </label>
        )}
      </div>
    </fieldset>
  );
}
