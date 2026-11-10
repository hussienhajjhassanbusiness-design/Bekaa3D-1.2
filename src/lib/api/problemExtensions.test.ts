import { describe, it, expect } from "vitest";
import { readProblemInteger, readProblemString } from "./problemExtensions";
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
