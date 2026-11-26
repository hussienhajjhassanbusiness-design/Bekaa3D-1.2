import { describe, it, expect } from "vitest";
import { mapValidationErrorsToFields } from "./validationErrors";
import type { ValidationErrorItem } from "./ApiError";

// Phase 2 auth/account batch — "For form-field mapping: drop loc[0]
// ("body"/"query"/"path") and map the remaining path." Messages shown to
// the user are always frontend-owned/safe — never the backend's raw `msg`
// text (per the phase-2 error-contract rule) — only `type` selects which
// safe copy is shown.

describe("mapValidationErrorsToFields", () => {
  it("returns an empty array when there are no errors", () => {
    expect(mapValidationErrorsToFields(undefined)).toEqual([]);
    expect(mapValidationErrorsToFields([])).toEqual([]);
  });

  it("drops loc[0] (the body/query/path segment) and uses the remainder as the field name", () => {
    const errors: ValidationErrorItem[] = [{ loc: ["body", "email"], msg: "field required", type: "missing" }];

    const result = mapValidationErrorsToFields(errors);

    expect(result).toHaveLength(1);
    expect(result[0]?.field).toBe("email");
  });

  it("joins a nested remaining path with dots", () => {
    const errors: ValidationErrorItem[] = [
      { loc: ["body", "address", "city"], msg: "field required", type: "missing" },
    ];

    const result = mapValidationErrorsToFields(errors);

    expect(result[0]?.field).toBe("address.city");
  });

  it("stringifies a numeric loc segment (e.g. an array index) into the joined field path", () => {
    const errors: ValidationErrorItem[] = [
      { loc: ["body", "lines", 0, "quantity"], msg: "must be positive", type: "greater_than" },
    ];

    const result = mapValidationErrorsToFields(errors);

    expect(result[0]?.field).toBe("lines.0.quantity");
  });

  it("treats a loc with nothing left after dropping loc[0] as a form-level error (empty field)", () => {
    const errors: ValidationErrorItem[] = [{ loc: ["body"], msg: "Invalid JSON", type: "json_invalid" }];

    const result = mapValidationErrorsToFields(errors);

    expect(result[0]?.field).toBe("");
  });

  it("never renders the backend's own msg text — only a frontend-owned safe message, chosen by type", () => {
    const errors: ValidationErrorItem[] = [
      { loc: ["body", "email"], msg: "some backend-authored diagnostic text", type: "missing" },
    ];

    const result = mapValidationErrorsToFields(errors);

    expect(result[0]?.message).not.toBe("some backend-authored diagnostic text");
    expect(result[0]?.message).toBe("This field is required.");
  });

  it("maps string_too_short/string_too_long/extra_forbidden/value_error to distinct safe messages", () => {
    const errors: ValidationErrorItem[] = [
      { loc: ["body", "password"], msg: "x", type: "string_too_short" },
      { loc: ["body", "password"], msg: "x", type: "string_too_long" },
      { loc: ["body", "captcha_token"], msg: "x", type: "extra_forbidden" },
      { loc: ["body", "email"], msg: "x", type: "value_error" },
    ];

    const result = mapValidationErrorsToFields(errors);

    expect(result.map((item) => item.message)).toEqual([
      "This value is too short.",
      "This value is too long.",
      "This field isn't accepted by the server.",
      "Enter a valid value.",
    ]);
  });

  it("falls back to a generic safe message for an unrecognized type, never a crash", () => {
    const errors: ValidationErrorItem[] = [
      { loc: ["body", "email"], msg: "x", type: "some_future_error_type_not_in_the_table" },
    ];

    const result = mapValidationErrorsToFields(errors);

    expect(result[0]?.message).toBe("This value is invalid.");
  });

  it("maps every item in a multi-item array, preserving order", () => {
    const errors: ValidationErrorItem[] = [
      { loc: ["body", "email"], msg: "x", type: "missing" },
      { loc: ["body", "password"], msg: "x", type: "string_too_short" },
    ];

    const result = mapValidationErrorsToFields(errors);

    expect(result.map((item) => item.field)).toEqual(["email", "password"]);
  });
});
