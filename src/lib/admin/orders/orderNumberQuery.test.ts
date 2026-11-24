import { describe, it, expect } from "vitest";
import { ORDER_NUMBER_QUERY_MAX_LENGTH, normalizeOrderNumberQuery } from "./orderNumberQuery";

describe("normalizeOrderNumberQuery", () => {
  it("passes a real order number through unchanged", () => {
    expect(normalizeOrderNumberQuery("B3D-7NJV7HX7")).toBe("B3D-7NJV7HX7");
  });

  it("trims and upper-cases (order numbers are always upper case; the backend match is case-sensitive)", () => {
    expect(normalizeOrderNumberQuery("  b3d-7njv7hx7 ")).toBe("B3D-7NJV7HX7");
  });

  it("treats blank or whitespace-only input as no filter", () => {
    expect(normalizeOrderNumberQuery("")).toBeUndefined();
    expect(normalizeOrderNumberQuery("   ")).toBeUndefined();
  });

  it("never exceeds the backend's 40-character limit (a longer value would be a 422)", () => {
    expect(normalizeOrderNumberQuery("x".repeat(60))).toHaveLength(ORDER_NUMBER_QUERY_MAX_LENGTH);
    expect(ORDER_NUMBER_QUERY_MAX_LENGTH).toBe(40);
  });
});
