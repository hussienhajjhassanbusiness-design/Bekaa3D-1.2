import { describe, it, expect } from "vitest";
import { describeAddressWriteError } from "./addressErrors";
import type { ApiError } from "@/lib/api/ApiError";

// Branches on ApiError.kind / status / code only. Never returns the
// backend's own detail/title/msg text.

function http(status: number, code: string, extra: Partial<ApiError> = {}): ApiError {
  return {
    kind: "http",
    status,
    code,
    title: "SERVER TITLE",
    detail: "SERVER DETAIL must never be shown",
    message: "fallback",
    raw: {},
    ...extra,
  };
}

function allText(result: ReturnType<typeof describeAddressWriteError>): string {
  return [result.formMessage ?? "", ...result.fieldErrors.map((item) => item.message)].join(" ");
}

describe("describeAddressWriteError", () => {
  it("maps 422 VALIDATION_ERROR locations onto form fields with frontend-owned copy", () => {
    const result = describeAddressWriteError(
      http(422, "VALIDATION_ERROR", {
        errors: [
          { loc: ["body", "phone"], msg: "invalid value", type: "value_error" },
          { loc: ["body", "city"], msg: "invalid value", type: "value_error" },
          { loc: ["body", "label"], msg: "String should have at most 50 characters", type: "string_too_long" },
        ],
      })
    );
    expect(result.fieldErrors).toEqual([
      { field: "phone", message: "Enter a Lebanese phone number, e.g. 03 123 456 or +961 71 123 456." },
      { field: "city", message: "Enter a valid city." },
      { field: "label", message: "This value is too long." },
    ]);
    expect(result.formMessage).toMatch(/check the highlighted fields/i);
    expect(allText(result)).not.toContain("invalid value");
    expect(allText(result)).not.toContain("SERVER");
  });

  it("puts a validation error with no known field (e.g. a whole-body error) in the form-level message only", () => {
    const result = describeAddressWriteError(
      http(422, "VALIDATION_ERROR", { errors: [{ loc: ["body"], msg: "at least one field", type: "value_error" }] })
    );
    expect(result.fieldErrors).toEqual([]);
    expect(result.formMessage).toBeTruthy();
    expect(result.formMessage).not.toContain("at least one field");
  });

  it("422 ADDRESS_LIMIT_REACHED gets its own copy, not field errors", () => {
    const result = describeAddressWriteError(http(422, "ADDRESS_LIMIT_REACHED"));
    expect(result.fieldErrors).toEqual([]);
    expect(result.formMessage).toMatch(/address book is full/i);
    expect(result.limitReached).toBe(true);
  });

  it("403 EMAIL_VERIFICATION_REQUIRED asks the customer to verify their email", () => {
    expect(describeAddressWriteError(http(403, "EMAIL_VERIFICATION_REQUIRED")).formMessage).toMatch(/verify your email/i);
  });

  it("403 CSRF_INVALID and a local missing-CSRF failure both get the session copy", () => {
    expect(describeAddressWriteError(http(403, "CSRF_INVALID")).formMessage).toMatch(/verify your session/i);
    expect(describeAddressWriteError({ kind: "csrf", message: "x", raw: undefined }).formMessage).toMatch(
      /verify your session/i
    );
  });

  it("404 NOT_FOUND says the address no longer exists and flags it as gone", () => {
    const result = describeAddressWriteError(http(404, "NOT_FOUND"));
    expect(result.formMessage).toMatch(/no longer exists/i);
    expect(result.notFound).toBe(true);
  });

  it("401 AUTH_REQUIRED (after the one refresh failed) asks the customer to log in again", () => {
    expect(describeAddressWriteError(http(401, "AUTH_REQUIRED")).formMessage).toMatch(/log in again/i);
  });

  it("anything else (500, network, unknown code, a non-ApiError) gets safe generic copy", () => {
    for (const error of [
      http(500, "INTERNAL_ERROR"),
      http(409, "SOMETHING_NEW"),
      { kind: "network", message: "x", raw: undefined } as ApiError,
      new Error("boom"),
      undefined,
    ]) {
      const result = describeAddressWriteError(error);
      expect(result.formMessage).toBe("Something went wrong. Please try again.");
      expect(result.fieldErrors).toEqual([]);
    }
  });
});
