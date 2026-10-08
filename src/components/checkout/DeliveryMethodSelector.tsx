"use client";

import { useId, useState } from "react";
import type { AddressModel } from "@/lib/addresses/addressModel";
import type { ShippingZoneOption } from "@/lib/shippingZones/shippingZoneModels";
import type { DeliveryMethodSelection } from "@/lib/checkout/checkoutModels";

export interface DeliveryMethodSelectorProps {
  addresses: readonly AddressModel[];
  zones: readonly ShippingZoneOption[];
  selection: DeliveryMethodSelection | null;
  // `null` is a real argument, not an absence of one: it invalidates
  // a stale complete selection the instant the user starts choosing a
  // different address, so the caller's authoritative state never
  // disagrees with what the UI currently shows (a real gap found by
  // independent review — plan §5 follow-up).
  onSelect: (selection: DeliveryMethodSelection | null) => void;
  // Rendered only when explicitly true — pickup availability is
  // unconfirmed (FVS-026-IMPLEMENTATION-PLAN.md §0), so no caller
  // means no Pickup option, never an invented default.
  pickupAvailable?: boolean;
}

// #FVS026 — reuses FVS-023's AddressModel and FVS-024's
// ShippingZoneOption directly, no checkout-specific duplicate. No
// address-to-zone inference anywhere (#ARCHITECTURE-EXPLICIT-SHIPPING-ZONE,
// carried over from FVS-024): choosing an address never pre-fills a
// zone — the zone is always a separate, explicit control, and
// onSelect only fires once a complete selection exists.
export function DeliveryMethodSelector({ addresses, zones, selection, onSelect, pickupAvailable }: DeliveryMethodSelectorProps) {
  const groupName = useId();
  const [activeAddressId, setActiveAddressId] = useState<string | null>(
    selection?.kind === "address" ? selection.addressId : null
  );

  const isPickupSelected = selection?.kind === "pickup";
  const activeZoneId = selection?.kind === "address" && selection.addressId === activeAddressId ? selection.zoneId : "";

  function handleChooseAddress(addressId: string) {
    setActiveAddressId(addressId);
    // If a complete selection already existed for a DIFFERENT address
    // (or for pickup), it is now stale the instant the user starts
    // choosing this one — invalidate it immediately rather than
    // leaving the caller's authoritative state out of sync with the
    // visible UI. Choosing an address from a blank starting selection
    // (or re-clicking the address that already matches the current
    // complete selection) intentionally does not call onSelect at
    // all — a zone must still be chosen before any complete
    // DeliveryMethodSelection exists, and nothing was invalidated.
    const isStale = selection !== null && (selection.kind !== "address" || selection.addressId !== addressId);
    if (isStale) {
      onSelect(null);
    }
  }

  function handleChooseZone(addressId: string, zoneId: string) {
    if (!zoneId) {
      return;
    }
    onSelect({ kind: "address", addressId, zoneId });
  }

  function handleChoosePickup() {
    setActiveAddressId(null);
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
            <div key={address.id}>
              <label className="flex items-center gap-2 text-body text-text-primary">
                <input
                  type="radio"
                  name={groupName}
                  checked={isActive}
                  onChange={() => handleChooseAddress(address.id)}
                />
                {label}
              </label>
              {isActive && (
                <select
                  aria-label="Shipping zone"
                  value={activeZoneId}
                  onChange={(event) => handleChooseZone(address.id, event.target.value)}
                  className="mt-1 ml-6 rounded-sm border border-border-default px-2 py-1 text-body"
                >
                  <option value="">Select a shipping zone</option>
                  {zones.map((zone) => (
                    <option key={zone.id} value={zone.id}>
                      {zone.displayName}
                    </option>
                  ))}
                </select>
              )}
            </div>
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
