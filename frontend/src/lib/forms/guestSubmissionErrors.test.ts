import { describe, it, expect } from "vitest";
import type { ApiError } from "@/lib/api/ApiError";
import { CAPTCHA_FAILURE_COPY } from "@/lib/captcha/captchaErrors";
import { describeGuestSubmissionFailure, GUEST_SUBMISSION_COPY } from "./guestSubmissionErrors";
import { isPhoneShaped } from "./guestFieldRules";

const LABELS = { name: "Name", email: "Email", phone: "Phone" };

function http(status: number, extra: Partial<ApiError> = {}): ApiError {
  return { kind: "http", status, message: "x", detail: "RAW BACKEND DETAIL", raw: {}, ...extra };
}

describe("describeGuestSubmissionFailure", () => {
  it("maps captcha refusals to the shared captcha copy", () => {
    expect(describeGuestSubmissionFailure(http(400, { code: "CAPTCHA_INVALID" }), LABELS).message).toBe(CAPTCHA_FAILURE_COPY.invalid);
    expect(describeGuestSubmissionFailure(http(503, { code: "SERVICE_UNAVAILABLE" }), LABELS).message).toBe(CAPTCHA_FAILURE_COPY.unavailable);
  });

  it("names the flagged fields of a 422 with frontend labels, never the server msg", () => {
    const result = describeGuestSubmissionFailure(
      http(422, {
        code: "VALIDATION_ERROR",
        errors: [
          { loc: ["body", "email"], msg: "RAW MSG", type: "value_error" },
          { loc: ["body", "phone"], msg: "RAW MSG", type: "value_error" },
        ],
      }),
      LABELS
    );
    expect(result).toEqual({ message: "Please check: Email, Phone.", fields: ["email", "phone"] });
    expect(result.message).not.toMatch(/RAW/);
  });

  it("falls back to generic invalid copy for a model-level 422", () => {
    const result = describeGuestSubmissionFailure(http(422, { errors: [{ loc: ["body"], msg: "RAW", type: "value_error" }] }), LABELS);
    expect(result).toEqual({ message: GUEST_SUBMISSION_COPY.invalid, fields: [] });
  });

  it("uses Retry-After for rate limits when present", () => {
    expect(describeGuestSubmissionFailure(http(429, { retryAfterSeconds: 1800 }), LABELS).message).toBe(
      "Too many submissions. Please try again in about 30 minutes."
    );
    expect(describeGuestSubmissionFailure(http(429), LABELS).message).toBe(GUEST_SUBMISSION_COPY.rateLimited);
  });

  it("covers network, timeout, 5xx and non-errors safely", () => {
    expect(describeGuestSubmissionFailure({ kind: "network", message: "x", raw: undefined }, LABELS).message).toBe(GUEST_SUBMISSION_COPY.network);
    expect(describeGuestSubmissionFailure({ kind: "timeout", message: "x", raw: undefined }, LABELS).message).toBe(GUEST_SUBMISSION_COPY.timeout);
    expect(describeGuestSubmissionFailure(http(500), LABELS).message).toBe(GUEST_SUBMISSION_COPY.generic);
    expect(describeGuestSubmissionFailure(new Error("boom"), LABELS).message).toBe(GUEST_SUBMISSION_COPY.generic);
  });
});

describe("isPhoneShaped (mirrors backend phone_shaped)", () => {
  it("accepts phone-shaped values with at least 6 digits", () => {
    expect(isPhoneShaped("+961 70 123 456")).toBe(true);
    expect(isPhoneShaped("(01) 234-567")).toBe(true);
  });
  it("refuses letters, too few digits and over-long values", () => {
    expect(isPhoneShaped("call me")).toBe(false);
    expect(isPhoneShaped("12-34-5")).toBe(false);
    expect(isPhoneShaped("1".repeat(33))).toBe(false);
  });
});
