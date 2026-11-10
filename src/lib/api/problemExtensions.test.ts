import { describe, it, expect } from "vitest";
import { readProblemArray, readProblemInteger, readProblemString } from "./problemExtensions";
import type { ApiError } from "./ApiError";

// RFC 9457 extension members (e.g. QUANTITY_EXCEEDS_LIMIT's
// `max_quantity`) live at the top level of the Problem body, which
// parseProblemBody keeps untouched in `raw`. These readers are strict:
// a wrong type is treated as absent, never coerced.

function error(raw: unknown): ApiError {
  return { kind: "http", status: 422, code: "X", message: "m", raw };
}

describe("readProblemInteger", () => {
  it("reads a top-level integer member", () => {
    expect(readProblemInteger(error({ max_quantity: 5 }), "max_quantity")).toBe(5);
  });

  it.each([["5"], [5.5], [null], [undefined], [Number.NaN]])("treats %p as absent", (value) => {
    expect(readProblemInteger(error({ max_quantity: value }), "max_quantity")).toBeUndefined();
  });

  it("is undefined when raw is not an object", () => {
    expect(readProblemInteger(error("text"), "max_quantity")).toBeUndefined();
    expect(readProblemInteger(error([1]), "0")).toBeUndefined();
  });
});

describe("readProblemString", () => {
  it("reads a top-level string member", () => {
    expect(readProblemString(error({ reason: "unavailable" }), "reason")).toBe("unavailable");
  });

  it("treats a non-string as absent", () => {
    expect(readProblemString(error({ reason: 3 }), "reason")).toBeUndefined();
  });
});

describe("readProblemArray (Phase 5D)", () => {
  const err = (raw: unknown) => ({
    kind: "http" as const,
    status: 409,
    message: "x",
    raw,
  });

  it("returns an array member as-is; elements are validated by the caller", () => {
    expect(readProblemArray(err({ price_changes: [{ a: 1 }] }), "price_changes")).toEqual([{ a: 1 }]);
  });

  it("treats a missing or non-array member as absent", () => {
    expect(readProblemArray(err({}), "lines")).toBeUndefined();
    expect(readProblemArray(err({ lines: "nope" }), "lines")).toBeUndefined();
    expect(readProblemArray(err({ lines: { 0: 1 } }), "lines")).toBeUndefined();
    expect(readProblemArray(err(null), "lines")).toBeUndefined();
  });
});
