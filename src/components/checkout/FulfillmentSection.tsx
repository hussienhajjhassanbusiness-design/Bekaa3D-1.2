"use client";

import Link from "next/link";
import { useId } from "react";
import { Button } from "@/components/forms/Button";
import { TextField } from "@/components/forms/TextField";
import type { AddressModel } from "@/lib/addresses/addressModel";
import { FULFILLMENT_COPY } from "@/lib/checkout/checkoutCopy";
import type { PickupOption } from "@/lib/checkout/checkoutEligibility";
import { MAX_CONTACT_PHONE } from "@/lib/checkout/checkoutPayload";
import type { FulfillmentMethod } from "@/lib/checkout/checkoutTypes";

export interface FulfillmentSectionProps {
  value: FulfillmentMethod | null;
  onChange: (method: FulfillmentMethod) => void;
  addresses: readonly AddressModel[];
  addressesLoading: boolean;
  addressesError: boolean;
  onRetryAddresses: () => void;
  addressId: string | null;
  onAddressChange: (addressId: string) => void;
  contactPhone: string;
  onContactPhoneChange: (value: string) => void;
  pickup: PickupOption;
  errors: { fulfillment?: string; addressId?: string; contactPhone?: string };
  disabled?: boolean;
}

const legendClass = "mb-2 text-h4 font-semibold text-text-primary";
const radioRowClass =
  "flex items-start gap-2 rounded-md border border-border-default bg-white p-3 text-body text-text-primary";

// #FVS026-FULFILLMENT
//
// Physical orders only (an STL-only order sends no fulfillment at all).
// Exactly the backend's two methods: delivery (to one of the customer's
// saved addresses; the courier calls the address's own phone, so no
// contact phone is sent) or pickup (a contact phone, no address; offered
// only when the shop has a pickup address). ADR-024: no shipping zone, no
// shipping charge on the website, no estimate. The address list is the
// canonical FVS-023 address-book query, reused as-is.
export function FulfillmentSection(props: FulfillmentSectionProps) {
  const { value, onChange, pickup, errors, disabled } = props;
  const methodErrorId = useId();

  return (
    <div className="flex flex-col gap-4">
      <fieldset disabled={disabled} aria-describedby={errors.fulfillment ? methodErrorId : undefined}>
        <legend className={legendClass}>Delivery or pickup</legend>
        <div className="flex flex-col gap-2">
          <label className={radioRowClass}>
            <input
              type="radio"
              name="fulfillment"
              className="mt-1"
              checked={value === "delivery"}
              onChange={() => onChange("delivery")}
            />
            <span>
              <span className="block font-semibold">Delivery</span>
              <span className="block text-caption text-text-secondary">{FULFILLMENT_COPY.deliveryHint}</span>
            </span>
          </label>
          {pickup.available && (
            <label className={radioRowClass}>
              <input
                type="radio"
                name="fulfillment"
                className="mt-1"
                checked={value === "pickup"}
                onChange={() => onChange("pickup")}
              />
              <span>
                <span className="block font-semibold">Pickup</span>
                <span className="block text-caption text-text-secondary">{FULFILLMENT_COPY.pickupHint}</span>
              </span>
            </label>
          )}
        </div>
        {errors.fulfillment && (
          <p id={methodErrorId} className="mt-1 text-caption text-danger">
            {errors.fulfillment}
          </p>
        )}
      </fieldset>

      {value === "delivery" && <DeliveryAddressPicker {...props} />}
      {value === "pickup" && <PickupDetails {...props} />}
    </div>
  );
}

function DeliveryAddressPicker({
  addresses,
  addressesLoading,
  addressesError,
  onRetryAddresses,
  addressId,
  onAddressChange,
  errors,
  disabled,
}: FulfillmentSectionProps) {
  const errorId = useId();

  if (addressesLoading) {
    return (
      <p role="status" className="text-body text-text-secondary">
        Loading your addresses…
      </p>
    );
  }
  if (addressesError) {
    return (
      <div className="flex flex-col items-start gap-2">
        <p role="alert" className="text-body text-danger">
          We couldn&apos;t load your addresses.
        </p>
        <Button type="button" variant="secondary" onClick={onRetryAddresses}>
          Retry
        </Button>
      </div>
    );
  }

  return (
    <fieldset disabled={disabled} aria-describedby={errors.addressId ? errorId : undefined}>
      <legend className={legendClass}>Delivery address</legend>
      {addresses.length === 0 ? (
        <p className="text-body text-text-primary">
          You don&apos;t have a saved address yet.{" "}
          <Link href="/account/addresses" className="font-semibold text-brand-dark-green underline">
            Add an address
          </Link>{" "}
          in your account, then come back to check out.
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          {addresses.map((address) => (
            <label key={address.id} className={radioRowClass}>
              <input
                type="radio"
                name="delivery-address"
                className="mt-1"
                checked={addressId === address.id}
                onChange={() => onAddressChange(address.id)}
              />
              <span>
                <span className="block font-semibold">
                  {address.label}
                  {address.isDefault && <span className="ml-2 text-caption text-text-secondary">(default)</span>}
                </span>
                {address.displayLines.map((line) => (
                  <span key={line} className="block text-caption text-text-secondary">
                    {line}
                  </span>
                ))}
              </span>
            </label>
          ))}
          <Link href="/account/addresses" className="text-caption font-semibold text-brand-dark-green underline">
            Manage addresses
          </Link>
        </div>
      )}
      {errors.addressId && (
        <p id={errorId} className="mt-1 text-caption text-danger">
          {errors.addressId}
        </p>
      )}
      <p className="mt-3 rounded-md bg-neutral-50 px-3 py-2 text-caption text-text-secondary">
        {FULFILLMENT_COPY.courierFee} The courier will call the phone number on the address you choose.
      </p>
    </fieldset>
  );
}

function PickupDetails({ pickup, contactPhone, onContactPhoneChange, errors, disabled }: FulfillmentSectionProps) {
  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-md bg-neutral-50 px-3 py-2 text-body text-text-primary">
        <p className="font-semibold">Pickup location</p>
        {pickup.address && <p className="whitespace-pre-line">{pickup.address}</p>}
        {pickup.hours && <p className="whitespace-pre-line text-caption text-text-secondary">{pickup.hours}</p>}
      </div>
      <TextField
        label="Contact phone"
        hint="A Lebanese number, for example 70 123 456. We'll use it to arrange your pickup."
        type="tel"
        autoComplete="tel"
        inputMode="tel"
        maxLength={MAX_CONTACT_PHONE}
        value={contactPhone}
        onChange={(event) => onContactPhoneChange(event.target.value)}
        error={errors.contactPhone}
        disabled={disabled}
      />
    </div>
  );
}
