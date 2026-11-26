import type { ApiError } from "@/lib/api/ApiError";
import { describeAdminError } from "@/lib/admin/adminErrorMessages";
import {
  PROMOTION_BADGE_MAX,
  PROMOTION_NAME_MAX,
  PROMOTION_SELECTED_MAX,
  type AdminPromotionRead,
  type AdminPromotionWrite,
  type DiscountType,
  type PromotionScope,
} from "@/lib/promotions/promotionTypes";

// #ADMIN-PROMOTION-FORM-MODEL
//
// The create/edit form's local draft and its conversions. The backend
// (docs/promotions.md) is the authority for every rule; the checks here only
// catch obvious input mistakes before a round trip and mirror the server's
// own limits. Dates are edited as the admin's local time (<input
// type="datetime-local">) and sent as UTC instants with an offset.

export interface PromotionFormValues {
  name: string;
  badgeText: string;
  discountType: DiscountType;
  percentText: string;
  fixedCents: number | null;
  scope: PromotionScope;
  productIds: readonly string[];
  startsAt: string;
  endsAt: string;
  active: boolean;
}

export type PromotionFormField =
  | "name"
  | "badgeText"
  | "discountValue"
  | "scope"
  | "productIds"
  | "startsAt"
  | "endsAt";

export type PromotionFormErrors = Partial<Record<PromotionFormField, string>>;

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

/** An instant as the value of a datetime-local input, in the browser's zone. */
export function toLocalInput(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** A datetime-local value (local time) as a UTC instant, or null if unparseable. */
export function fromLocalInput(value: string): string | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

export function emptyPromotionForm(now: Date = new Date()): PromotionFormValues {
  const start = new Date(now);
  start.setSeconds(0, 0);
  const end = new Date(start);
  end.setDate(end.getDate() + 7);
  return {
    name: "",
    badgeText: "",
    discountType: "percentage",
    percentText: "",
    fixedCents: null,
    scope: "all",
    productIds: [],
    startsAt: toLocalInput(start.toISOString()),
    endsAt: toLocalInput(end.toISOString()),
    active: true,
  };
}

export function promotionFormFrom(read: AdminPromotionRead): PromotionFormValues {
  return {
    name: read.name,
    badgeText: read.badge_text ?? "",
    discountType: read.discount_type,
    percentText: read.discount_type === "percentage" ? String(read.discount_value) : "",
    fixedCents: read.discount_type === "fixed" ? read.discount_value : null,
    scope: read.scope,
    productIds: [...read.product_ids],
    startsAt: toLocalInput(read.starts_at),
    endsAt: toLocalInput(read.ends_at),
    active: read.active,
  };
}

function discountValue(values: PromotionFormValues): number | null {
  if (values.discountType === "fixed") return values.fixedCents;
  const text = values.percentText.trim();
  return /^\d+$/.test(text) ? Number(text) : null;
}

export function validatePromotionForm(values: PromotionFormValues): PromotionFormErrors {
  const errors: PromotionFormErrors = {};
  const name = values.name.trim();
  if (!name) errors.name = "Enter a promotion name.";
  else if (name.length > PROMOTION_NAME_MAX) errors.name = `Use at most ${PROMOTION_NAME_MAX} characters.`;
  if (values.badgeText.trim().length > PROMOTION_BADGE_MAX) {
    errors.badgeText = `Use at most ${PROMOTION_BADGE_MAX} characters.`;
  }
  const value = discountValue(values);
  if (values.discountType === "percentage") {
    if (value === null || value < 1 || value > 100) errors.discountValue = "Enter a whole percentage from 1 to 100.";
  } else if (value === null || value < 1) {
    errors.discountValue = "Enter a discount amount above zero.";
  }
  if (values.scope === "selected") {
    if (values.productIds.length === 0) errors.productIds = "Choose at least one product.";
    else if (values.productIds.length > PROMOTION_SELECTED_MAX) {
      errors.productIds = `Choose at most ${PROMOTION_SELECTED_MAX} products.`;
    }
  }
  const start = fromLocalInput(values.startsAt);
  const end = fromLocalInput(values.endsAt);
  if (!start) errors.startsAt = "Enter a start date and time.";
  if (!end) errors.endsAt = "Enter an end date and time.";
  else if (start && end <= start) errors.endsAt = "The end must be after the start.";
  return errors;
}

/** The request body. Call only after `validatePromotionForm` returned no errors. */
export function toPromotionWrite(values: PromotionFormValues): AdminPromotionWrite {
  const badge = values.badgeText.trim();
  return {
    name: values.name.trim(),
    badge_text: badge ? badge : null,
    discount_type: values.discountType,
    discount_value: discountValue(values) ?? 0,
    scope: values.scope,
    product_ids: values.scope === "selected" ? [...values.productIds] : [],
    starts_at: fromLocalInput(values.startsAt) ?? "",
    ends_at: fromLocalInput(values.endsAt) ?? "",
    active: values.active,
  };
}

const SERVER_FIELDS: Record<string, PromotionFormField> = {
  name: "name",
  badge_text: "badgeText",
  discount_value: "discountValue",
  discount_type: "discountValue",
  scope: "scope",
  product_ids: "productIds",
  starts_at: "startsAt",
  ends_at: "endsAt",
};

const SERVER_FIELD_MESSAGES: Record<PromotionFormField, string> = {
  name: "Enter a valid promotion name.",
  badgeText: `Use at most ${PROMOTION_BADGE_MAX} characters.`,
  discountValue: "Enter a valid discount for this type.",
  scope: "Choose what the promotion applies to.",
  productIds: "Choose existing products only.",
  startsAt: "Enter a valid start date and time.",
  endsAt: "The end must be after the start.",
};

function isApiError(value: unknown): value is ApiError {
  return typeof value === "object" && value !== null && "kind" in value;
}

/** A server refusal as safe, frontend-owned copy: per field when the server names one. */
export function describePromotionError(error: unknown): { fieldErrors?: PromotionFormErrors; banner?: string } {
  if (isApiError(error) && error.kind === "http" && error.code === "VALIDATION_ERROR") {
    const fieldErrors: PromotionFormErrors = {};
    for (const item of error.errors ?? []) {
      const field = SERVER_FIELDS[String(item.loc[item.loc.length - 1])];
      if (field) fieldErrors[field] = SERVER_FIELD_MESSAGES[field];
    }
    if (Object.keys(fieldErrors).length > 0) return { fieldErrors };
  }
  return { banner: describeAdminError(error) };
}
