import { describe, it, expect } from "vitest";
import type { ApiError } from "@/lib/api/ApiError";
import {
  CAPTCHA_FAILURE_COPY,
  classifyCaptchaFailure,
  captchaFailureMessage,
  CAPTCHA_INVALID_CODE,
} from "./captchaErrors";

function http(status: number, extra: Partial<ApiError> = {}): ApiError {
  return { kind: "http", status, message: "x", raw: { detail: "RAW BACKEND DETAIL" }, ...extra };
}

describe("classifyCaptchaFailure", () => {
  it("maps 400 CAPTCHA_INVALID to 'invalid'", () => {
    expect(classifyCaptchaFailure(http(400, { code: CAPTCHA_INVALID_CODE }))).toBe("invalid");
  });

  it("does not treat a 400 with another code as a captcha failure", () => {
    expect(classifyCaptchaFailure(http(400, { code: "MALFORMED_REQUEST" }))).toBeNull();
  });

  it("maps 503 (captcha verification unavailable) to 'unavailable', whatever its code", () => {
    expect(classifyCaptchaFailure(http(503, { code: "SERVICE_UNAVAILABLE", retryAfterSeconds: 30 }))).toBe(
      "unavailable"
    );
    expect(classifyCaptchaFailure(http(503))).toBe("unavailable");
  });

  it("maps a 422 whose validation error points at body.captcha_token to 'missing'", () => {
    const error = http(422, {
      code: "VALIDATION_ERROR",
      errors: [{ loc: ["body", "captcha_token"], msg: "Field required", type: "missing" }],
    });
    expect(classifyCaptchaFailure(error)).toBe("missing");
  });

  it("does not claim a 422 on another field", () => {
    const error = http(422, { errors: [{ loc: ["body", "email"], msg: "bad", type: "value_error" }] });
    expect(classifyCaptchaFailure(error)).toBeNull();
  });

  it("returns null for non-http errors and non-ApiError values", () => {
    expect(classifyCaptchaFailure({ kind: "network", message: "x", raw: undefined })).toBeNull();
    expect(classifyCaptchaFailure(new Error("boom"))).toBeNull();
    expect(classifyCaptchaFailure(undefined)).toBeNull();
  });
});

describe("captchaFailureMessage", () => {
  it("returns frontend-owned copy, never backend detail", () => {
    for (const kind of ["invalid", "unavailable", "missing"] as const) {
      const message = captchaFailureMessage(kind);
      expect(message).toBe(CAPTCHA_FAILURE_COPY[kind]);
      expect(message).not.toMatch(/RAW BACKEND DETAIL/);
      expect(message.length).toBeGreaterThan(0);
    }
  });

  it("uses distinct copy for unavailable vs invalid", () => {
    expect(captchaFailureMessage("unavailable")).not.toBe(captchaFailureMessage("invalid"));
  });
});
