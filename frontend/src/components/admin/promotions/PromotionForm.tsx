"use client";

import Link from "next/link";
import { useId } from "react";
import { AdminSection } from "@/components/admin/adminUi";
import { Button, buttonLinkClassName } from "@/components/forms/Button";
import { MoneyInput } from "@/components/forms/MoneyInput";
import { SelectField } from "@/components/forms/SelectField";
import { TextField } from "@/components/forms/TextField";
import { PromotionProductPicker } from "./PromotionProductPicker";
import type { PromotionFormErrors, PromotionFormValues } from "@/lib/admin/promotions/promotionForm";
import { promotionScopeLabel } from "@/lib/promotions/promotionFormat";
import {
  PROMOTION_BADGE_MAX,
  PROMOTION_CURRENCY,
  PROMOTION_NAME_MAX,
  type DiscountType,
  type PromotionScope,
} from "@/lib/promotions/promotionTypes";

export interface PromotionFormProps {
  value: PromotionFormValues;
  onChange: (next: PromotionFormValues) => void;
  errors?: PromotionFormErrors;
  isSubmitting: boolean;
  submitLabel: string;
  onSubmit: () => void;
}

const SCOPES: readonly PromotionScope[] = ["all", "physical", "stl", "selected"];

// #ADMIN-PROMOTION-FORM — one professional form, one Save action (Stitch
// admin forms: AdminSection cards, COMPONENT-SPECS §27 fields, §29 switch).
// Only the fields the backend contract has: name, badge text, discount type
// and value, scope (+ products for `selected`), the window, and `active`.
// Category scope, coupon codes and stacking do not exist and are not offered.
export function PromotionForm({ value, onChange, errors, isSubmitting, submitLabel, onSubmit }: PromotionFormProps) {
  const activeLabelId = useId();
  const activeHintId = useId();

  function set<K extends keyof PromotionFormValues>(key: K, next: PromotionFormValues[K]) {
    onChange({ ...value, [key]: next });
  }

  return (
    <form
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
      className="flex max-w-form flex-col gap-6"
    >
      <fieldset disabled={isSubmitting} className="flex flex-col gap-6">
        <AdminSection title="Campaign">
          <TextField
            label="Promotion name"
            hint="Shown to customers, e.g. on the homepage banner and product pages."
            value={value.name}
            maxLength={PROMOTION_NAME_MAX}
            onChange={(event) => set("name", event.target.value)}
            error={errors?.name}
          />
          <TextField
            label="Badge text (optional)"
            hint="A short label above the banner headline."
            value={value.badgeText}
            maxLength={PROMOTION_BADGE_MAX}
            onChange={(event) => set("badgeText", event.target.value)}
            error={errors?.badgeText}
          />
        </AdminSection>

        <AdminSection title="Discount">
          <SelectField
            label="Discount type"
            value={value.discountType}
            onChange={(event) => set("discountType", event.target.value as DiscountType)}
          >
            <option value="percentage">Percentage</option>
            <option value="fixed">Fixed amount</option>
          </SelectField>
          {value.discountType === "percentage" ? (
            <TextField
              label="Discount value (%)"
              hint="A whole number from 1 to 100."
              type="number"
              inputMode="numeric"
              min={1}
              max={100}
              step={1}
              value={value.percentText}
              onChange={(event) => set("percentText", event.target.value)}
              error={errors?.discountValue}
            />
          ) : (
            <MoneyInput
              label="Discount value"
              hint="Taken off each covered product's price; a price never goes below zero."
              currencyLabel={PROMOTION_CURRENCY}
              valueCents={value.fixedCents}
              onChangeCents={(cents) => set("fixedCents", cents)}
              error={errors?.discountValue}
            />
          )}
          <p className="text-xs text-on-surface-variant">
            The shop works out each discounted price itself. When more than one promotion covers a product, only the one
            giving the lowest price applies — promotions never stack.
          </p>
        </AdminSection>

        <AdminSection title="Products">
          <SelectField
            label="Applies to"
            value={value.scope}
            onChange={(event) => set("scope", event.target.value as PromotionScope)}
            // A product-list refusal belongs to the picker when it is shown,
            // else here, so it is never silently dropped.
            error={errors?.scope ?? (value.scope === "selected" ? undefined : errors?.productIds)}
          >
            {SCOPES.map((scope) => (
              <option key={scope} value={scope}>
                {promotionScopeLabel(scope)}
              </option>
            ))}
          </SelectField>
          {value.scope === "selected" && (
            <PromotionProductPicker
              selectedIds={value.productIds}
              onChange={(ids) => set("productIds", ids)}
              error={errors?.productIds}
              disabled={isSubmitting}
            />
          )}
        </AdminSection>

        <AdminSection title="Schedule">
          <div className="grid gap-4 tablet:grid-cols-2">
            <TextField
              label="Start"
              type="datetime-local"
              value={value.startsAt}
              onChange={(event) => set("startsAt", event.target.value)}
              error={errors?.startsAt}
            />
            <TextField
              label="End"
              hint="The promotion stops at this moment."
              type="datetime-local"
              value={value.endsAt}
              onChange={(event) => set("endsAt", event.target.value)}
              error={errors?.endsAt}
            />
          </div>
          <div className="flex items-start justify-between gap-4">
            <div>
              <span id={activeLabelId} className="font-label text-label-sm uppercase text-on-surface">
                Active
              </span>
              <p id={activeHintId} className="mt-1 text-xs text-on-surface-variant">
                Switch off to stop the promotion at once, whatever its dates.
              </p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={value.active}
              aria-labelledby={activeLabelId}
              aria-describedby={activeHintId}
              onClick={() => set("active", !value.active)}
              className={`inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors duration-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary motion-reduce:transition-none ${
                value.active ? "bg-primary" : "bg-outline"
              }`}
            >
              <span
                aria-hidden="true"
                className={`h-5 w-5 rounded-full bg-surface-container-lowest shadow-sm transition-transform duration-200 motion-reduce:transition-none ${
                  value.active ? "translate-x-5" : "translate-x-0.5"
                }`}
              />
            </button>
          </div>
        </AdminSection>
      </fieldset>

      <div className="flex flex-wrap justify-end gap-3">
        <Link href="/admin/promotions" className={buttonLinkClassName("outline")}>
          Cancel
        </Link>
        <Button type="submit" isLoading={isSubmitting}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
