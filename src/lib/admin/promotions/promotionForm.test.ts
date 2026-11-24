import { describe, it, expect } from "vitest";
import {
  describePromotionError,
  emptyPromotionForm,
  fromLocalInput,
  promotionFormFrom,
  toLocalInput,
  toPromotionWrite,
  validatePromotionForm,
  type PromotionFormValues,
} from "./promotionForm";
import type { AdminPromotionRead } from "@/lib/promotions/promotionTypes";

function form(over: Partial<PromotionFormValues> = {}): PromotionFormValues {
  return {
    ...emptyPromotionForm(new Date("2026-12-01T10:00:00Z")),
    name: "Eid Sale",
    percentText: "20",
    ...over,
  };
}

const READ: AdminPromotionRead = {
  id: "p-1",
  name: "Christmas Sale",
  badge_text: "Xmas",
  discount_type: "fixed",
  discount_value: 500,
  scope: "selected",
  product_ids: ["a", "b"],
  starts_at: "2026-12-20T08:00:00Z",
  ends_at: "2026-12-27T08:00:00Z",
  active: false,
  status: "inactive",
  created_at: "2026-12-01T00:00:00Z",
  updated_at: "2026-12-01T00:00:00Z",
};

describe("promotion form", () => {
  it("accepts a complete percentage promotion and builds the exact request body", () => {
    const values = form();
    expect(validatePromotionForm(values)).toEqual({});
    const body = toPromotionWrite(values);
    expect(body).toMatchObject({
      name: "Eid Sale",
      badge_text: null,
      discount_type: "percentage",
      discount_value: 20,
      scope: "all",
      product_ids: [],
      active: true,
    });
    expect(new Date(body.ends_at).getTime() - new Date(body.starts_at).getTime()).toBe(7 * 24 * 3600 * 1000);
    expect(body.starts_at).toMatch(/Z$/);
  });

  it.each([
    [{ percentText: "0" }, "discountValue"],
    [{ percentText: "101" }, "discountValue"],
    [{ percentText: "12.5" }, "discountValue"],
    [{ discountType: "fixed" as const, fixedCents: null }, "discountValue"],
    [{ name: "  " }, "name"],
    [{ scope: "selected" as const, productIds: [] }, "productIds"],
    [{ endsAt: "2026-11-01T10:00" }, "endsAt"],
    [{ startsAt: "" }, "startsAt"],
  ])("refuses %o", (over, field) => {
    expect(validatePromotionForm(form(over))).toHaveProperty(field);
  });

  it("sends cents for a fixed discount and product ids only for a selected scope", () => {
    const body = toPromotionWrite(form({ discountType: "fixed", fixedCents: 250, scope: "stl", productIds: ["x"] }));
    expect(body).toMatchObject({ discount_type: "fixed", discount_value: 250, scope: "stl", product_ids: [] });
  });

  it("starts an edit from the server's promotion and round-trips the window", () => {
    const values = promotionFormFrom(READ);
    expect(values).toMatchObject({
      name: "Christmas Sale",
      badgeText: "Xmas",
      discountType: "fixed",
      fixedCents: 500,
      scope: "selected",
      productIds: ["a", "b"],
      active: false,
    });
    expect(fromLocalInput(values.startsAt)).toBe(READ.starts_at.replace("Z", ".000Z"));
    expect(fromLocalInput(toLocalInput(READ.ends_at))).toBe("2026-12-27T08:00:00.000Z");
  });

  it("maps a server VALIDATION_ERROR onto its fields with safe copy", () => {
    const result = describePromotionError({
      kind: "http",
      status: 422,
      code: "VALIDATION_ERROR",
      message: "RAW",
      errors: [{ loc: ["body", "ends_at"], msg: "RAW must be after", type: "value_error" }],
    });
    expect(result).toEqual({ fieldErrors: { endsAt: "The end must be after the start." } });
  });

  it("falls back to the shared admin copy for anything else", () => {
    expect(describePromotionError({ kind: "http", status: 403, code: "CSRF_INVALID", message: "RAW" }).banner).not.toMatch(
      /RAW/
    );
  });
});
