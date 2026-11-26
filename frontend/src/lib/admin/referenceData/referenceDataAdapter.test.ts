import { describe, it, expect } from "vitest";
import { toReferenceDataEntry, toCreateInput, describeReferenceDataError } from "./referenceDataAdapter";
import type { RawReferenceDetail } from "./referenceDataAdminTypes";

function rawDetail(overrides: Partial<RawReferenceDetail>): RawReferenceDetail {
  return {
    id: "c1",
    name: "Toys",
    is_active: true,
    deleted_at: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("toReferenceDataEntry", () => {
  it("maps a live category, carrying slug into swatchValue", () => {
    expect(toReferenceDataEntry(rawDetail({ slug: "toys" }))).toMatchObject({
      id: "c1",
      name: "Toys",
      isArchived: false,
      isActive: true,
      swatchValue: "toys",
    });
  });

  it("maps an archived entry from deleted_at", () => {
    expect(toReferenceDataEntry(rawDetail({ deleted_at: "2026-02-01T00:00:00Z" }))).toMatchObject({
      isArchived: true,
    });
  });

  it("maps a disabled (but not archived) entry", () => {
    expect(toReferenceDataEntry(rawDetail({ is_active: false }))).toMatchObject({
      isArchived: false,
      isActive: false,
    });
  });

  it("leaves swatchValue undefined for a material/colour with no slug", () => {
    expect(toReferenceDataEntry(rawDetail({ name: "PLA" }))).toMatchObject({ swatchValue: undefined });
  });
});

describe("toCreateInput", () => {
  it("includes slug for categories", () => {
    expect(toCreateInput("categories", { name: "Toys", swatchValue: "toys" })).toEqual({ name: "Toys", slug: "toys" });
  });

  it("omits slug for materials/colours even if swatchValue is set", () => {
    expect(toCreateInput("materials", { name: "PLA", swatchValue: "irrelevant" })).toEqual({
      name: "PLA",
      slug: undefined,
    });
  });
});

describe("describeReferenceDataError", () => {
  it("maps SLUG_CONFLICT for categories onto the swatchValue (slug) field", () => {
    const result = describeReferenceDataError("categories", {
      kind: "http",
      status: 409,
      code: "SLUG_CONFLICT",
      message: "x",
      raw: undefined,
    });
    expect(result.fieldErrors).toEqual({ swatchValue: "That slug is already in use." });
  });

  it("maps SLUG_CONFLICT for materials/colours onto the name field", () => {
    const result = describeReferenceDataError("materials", {
      kind: "http",
      status: 409,
      code: "SLUG_CONFLICT",
      message: "x",
      raw: undefined,
    });
    expect(result.fieldErrors).toEqual({ name: "That name is already in use." });
  });

  it("maps CATEGORY_IN_USE to a banner message, not a field error", () => {
    const result = describeReferenceDataError("categories", {
      kind: "http",
      status: 409,
      code: "CATEGORY_IN_USE",
      message: "x",
      raw: undefined,
    });
    expect(result.fieldErrors).toBeUndefined();
    expect(result.bannerMessage).toMatch(/live product/i);
  });

  it("maps INVALID_STATE_TRANSITION to a banner message", () => {
    const result = describeReferenceDataError("colours", {
      kind: "http",
      status: 409,
      code: "INVALID_STATE_TRANSITION",
      message: "x",
      raw: undefined,
    });
    expect(result.bannerMessage).toBeTruthy();
    expect(result.fieldErrors).toBeUndefined();
  });

  it("falls back to a generic banner message for an unrecognized error", () => {
    const result = describeReferenceDataError("categories", { kind: "network", message: "x", raw: undefined });
    expect(result.bannerMessage).toBeTruthy();
  });
});
