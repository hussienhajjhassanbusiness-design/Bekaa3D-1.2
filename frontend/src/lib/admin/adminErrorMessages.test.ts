import { describe, it, expect } from "vitest";
import { describeAdminError } from "./adminErrorMessages";
import type { ApiError } from "@/lib/api/ApiError";

function httpError(code: string, status: number): ApiError {
  return { kind: "http", status, code, message: "x", raw: undefined };
}

// Phase 3 — bekaa3d-api-contract: branch on Problem.code, never on
// title/detail text. One shared mapper for the error codes that mean
// the same safe thing everywhere in the admin area (settings,
// customers, reference data, products, images) — never the raw
// backend `detail`/`title` string, per the login page's existing
// "frontend-owned safe copy" convention.
describe("describeAdminError", () => {
  it("returns a safe message for NOT_FOUND", () => {
    expect(describeAdminError(httpError("NOT_FOUND", 404))).toBe("This item could not be found. It may have been removed.");
  });

  it("returns a safe message for VERSION_CONFLICT", () => {
    expect(describeAdminError(httpError("VERSION_CONFLICT", 409))).toBe(
      "This item was changed by someone else. Review the latest version and try again."
    );
  });

  it("returns a safe message for SLUG_CONFLICT", () => {
    expect(describeAdminError(httpError("SLUG_CONFLICT", 409))).toBe("That name or slug is already in use.");
  });

  it("returns a safe message for CATEGORY_IN_USE", () => {
    expect(describeAdminError(httpError("CATEGORY_IN_USE", 409))).toBe(
      "This is still used by a live product. Reassign it before archiving."
    );
  });

  it("returns a safe message for INVALID_STATE_TRANSITION", () => {
    expect(describeAdminError(httpError("INVALID_STATE_TRANSITION", 409))).toBe(
      "This action can't be completed in the item's current state."
    );
  });

  it("returns a safe message for SETTING_INVALID", () => {
    expect(describeAdminError(httpError("SETTING_INVALID", 422))).toBe("Enter a valid value for this setting.");
  });

  it("returns a safe message for UPLOAD_REJECTED", () => {
    expect(describeAdminError(httpError("UPLOAD_REJECTED", 422))).toBe(
      "This file couldn't be uploaded. Use a JPEG, PNG or WebP image under 10 MB."
    );
  });

  it("returns a safe message for MALWARE_DETECTED", () => {
    expect(describeAdminError(httpError("MALWARE_DETECTED", 422))).toBe(
      "This file was rejected by the security scan and was not uploaded."
    );
  });

  it("returns a safe message for SERVICE_UNAVAILABLE", () => {
    expect(describeAdminError(httpError("SERVICE_UNAVAILABLE", 503))).toBe(
      "This service is temporarily unavailable. Please try again shortly."
    );
  });

  it("returns a safe message for RATE_LIMITED", () => {
    expect(describeAdminError(httpError("RATE_LIMITED", 429))).toBe("Too many requests. Please wait and try again.");
  });

  it("returns a safe message for VALIDATION_ERROR", () => {
    expect(describeAdminError(httpError("VALIDATION_ERROR", 422))).toBe("One or more fields are invalid.");
  });

  it("falls back to a generic message for an unrecognized code", () => {
    expect(describeAdminError(httpError("SOMETHING_ELSE", 418))).toBe("Something went wrong. Please try again.");
  });

  it("falls back to a generic message for a network error", () => {
    expect(describeAdminError({ kind: "network", message: "x", raw: undefined })).toBe(
      "We couldn't reach the server. Please try again."
    );
  });

  it("falls back to a generic message for a non-ApiError value", () => {
    expect(describeAdminError(new Error("boom"))).toBe("Something went wrong. Please try again.");
  });
});
