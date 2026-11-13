"use client";

import Link from "next/link";
import { useId } from "react";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { Button } from "@/components/forms/Button";
import { TextField } from "@/components/forms/TextField";
import { Icon } from "@/components/ui/Icon";
import type { AddressModel } from "@/lib/addresses/addressModel";
import { FULFILLMENT_COPY } from "@/lib/checkout/checkoutCopy";
import type { PickupOption } from "@/lib/checkout/checkoutEligibility";
import { MAX_CONTACT_PHONE } from "@/lib/checkout/checkoutPayload";
import type { FulfillmentMethod } from "@/lib/checkout/checkoutTypes";
import { CheckoutStepHeading } from "./CheckoutStepHeading";
import {
  CHOICE_CARD_CLASSES,
  CHOICE_HINT_CLASSES,
  CHOICE_INPUT_CLASSES,
  CHOICE_TITLE_CLASSES,
  FIELD_ERROR_CLASSES,
} from "./choiceCardStyles";

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
  // Presentation only (Batch 6): the step number and whether its choice is
  // made, for the numbered step header.
  step?: number;
  complete?: boolean;
}

const subLegendClass = "mb-3 font-label text-label-caps uppercase text-on-surface-variant";
const textLinkClass =
  "rounded-sm font-semibold text-primary underline decoration-1 underline-offset-4 hover:decoration-2";

// #FVS026-FULFILLMENT
//
// Physical orders only (an STL-only order sends no fulfillment at all).
// Exactly the backend's two methods: delivery (to one of the customer's
// saved addresses; the courier calls the address's own phone, so no
// contact phone is sent) or pickup (a contact phone, no address; offered
// only when the shop has a pickup address). ADR-024: no shipping zone, no
// shipping charge on the website, no estimate. The address list is the
// canonical FVS-023 address-book query, reused as-is.
//
// Redesign Batch 6: numbered step header as the legend, method and address
// choices as radio cards (native radios kept), courier-fee note as an info
// callout. No behaviour changed.
export function FulfillmentSection(props: FulfillmentSectionProps) {
  const { value, onChange, pickup, errors, disabled, step = 1, complete = false } = props;
  const methodErrorId = useId();

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <fieldset
        className="min-w-0"
        disabled={disabled}
        aria-describedby={errors.fulfillment ? methodErrorId : undefined}
      >
        <CheckoutStepHeading as="legend" step={step} title="Delivery or pickup" complete={complete} />
        <div className={`grid grid-cols-1 gap-3 ${pickup.available ? "tablet:grid-cols-2" : ""}`}>
          <label className={CHOICE_CARD_CLASSES}>
            <input
              type="radio"
              name="fulfillment"
              className={CHOICE_INPUT_CLASSES}
              checked={value === "delivery"}
              onChange={() => onChange("delivery")}
            />
            <span className="min-w-0 flex-1">
              <span className={CHOICE_TITLE_CLASSES}>Delivery</span>
              <span className={CHOICE_HINT_CLASSES}>{FULFILLMENT_COPY.deliveryHint}</span>
            </span>
            <Icon name="local-shipping" className="h-6 w-6 text-primary" />
          </label>
          {pickup.available && (
            <label className={CHOICE_CARD_CLASSES}>
              <input
                type="radio"
                name="fulfillment"
                className={CHOICE_INPUT_CLASSES}
                checked={value === "pickup"}
                onChange={() => onChange("pickup")}
              />
              <span className="min-w-0 flex-1">
                <span className={CHOICE_TITLE_CLASSES}>Pickup</span>
                <span className={CHOICE_HINT_CLASSES}>{FULFILLMENT_COPY.pickupHint}</span>
              </span>
              <Icon name="storefront" className="h-6 w-6 text-primary" />
            </label>
          )}
        </div>
        {errors.fulfillment && (
          <p id={methodErrorId} className={FIELD_ERROR_CLASSES}>
            <Icon name="error" className="mt-px h-4 w-4" />
            <span>{errors.fulfillment}</span>
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
      <div role="status" className="flex flex-col gap-3">
        <p className="text-body text-on-surface-variant">Loading your addresses…</p>
        <div
          aria-hidden="true"
          className="h-24 animate-pulse rounded-card bg-surface-container-low motion-reduce:animate-none"
        />
      </div>
    );
  }
  if (addressesError) {
    return (
      <div className="flex flex-col items-start gap-3 rounded-card border border-error/20 bg-error-container p-4">
        <p role="alert" className="flex items-start gap-2 text-body text-on-error-container">
          <Icon name="error" className="mt-px h-5 w-5 text-error" />
          <span>We couldn&apos;t load your addresses.</span>
        </p>
        <Button type="button" variant="secondary" onClick={onRetryAddresses}>
          Retry
        </Button>
      </div>
    );
  }

  return (
    <fieldset className="min-w-0" disabled={disabled} aria-describedby={errors.addressId ? errorId : undefined}>
      <legend className={subLegendClass}>Delivery address</legend>
      {addresses.length === 0 ? (
        <div className="flex items-start gap-3 rounded-card border border-dashed border-outline-variant bg-surface-container-low p-4 text-body text-on-surface">
          <Icon name="location-on" className="mt-px h-5 w-5 text-outline" />
          <p>
            You don&apos;t have a saved address yet.{" "}
            <Link href="/account/addresses" className={textLinkClass}>
              Add an address
            </Link>{" "}
            in your account, then come back to check out.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-1 gap-3 tablet:grid-cols-2">
            {addresses.map((address) => (
              <label key={address.id} className={CHOICE_CARD_CLASSES}>
                <input
                  type="radio"
                  name="delivery-address"
                  className={CHOICE_INPUT_CLASSES}
                  checked={addressId === address.id}
                  onChange={() => onAddressChange(address.id)}
                />
                <span className="min-w-0 flex-1 break-words">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className={CHOICE_TITLE_CLASSES}>{address.label}</span>
                    {address.isDefault && <StatusBadge label="Default" tone="positive" />}
                  </span>
                  {address.displayLines.map((line) => (
                    <span key={line} className={CHOICE_HINT_CLASSES}>
                      {line}
                    </span>
                  ))}
                </span>
              </label>
            ))}
          </div>
          <Link href="/account/addresses" className={`${textLinkClass} self-start py-2 text-caption`}>
            Manage addresses
          </Link>
        </div>
      )}
      {errors.addressId && (
        <p id={errorId} className={FIELD_ERROR_CLASSES}>
          <Icon name="error" className="mt-px h-4 w-4" />
          <span>{errors.addressId}</span>
        </p>
      )}
      <p className="mt-4 flex items-start gap-2 rounded-control border border-info-outline bg-info-container px-3 py-2 text-caption text-on-info-container">
        <Icon name="info" className="mt-px h-4 w-4 text-info" />
        <span>{FULFILLMENT_COPY.courierFee} The courier will call the phone number on the address you choose.</span>
      </p>
    </fieldset>
  );
}

function PickupDetails({ pickup, contactPhone, onContactPhoneChange, errors, disabled }: FulfillmentSectionProps) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start gap-3 rounded-card bg-surface-container-low p-4 text-body text-on-surface">
        <Icon name="storefront" className="mt-px h-5 w-5 text-primary" />
        <div className="min-w-0 break-words">
          <p className="font-label text-label-caps uppercase text-on-surface-variant">Pickup location</p>
          {pickup.address && <p className="mt-1 whitespace-pre-line">{pickup.address}</p>}
          {pickup.hours && (
            <p className="mt-1 whitespace-pre-line text-caption text-on-surface-variant">{pickup.hours}</p>
          )}
        </div>
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
