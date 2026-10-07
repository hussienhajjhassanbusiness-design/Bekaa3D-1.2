import { describe, it, expect } from "vitest";
import { GUEST_SUBMISSION_ERROR_COPY } from "./guestSubmissionFeedback";

// FVS-016-IMPLEMENTATION-PLAN.md T01 — one shared captcha/rate-limit/
// generic vocabulary for every guest (unauthenticated) submission flow
// (BYI, Contact, and future ones), so a visitor learns this interaction
// once rather than meeting slightly different copy per form.

describe("GUEST_SUBMISSION_ERROR_COPY", () => {
  it("has the exact captcha guidance", () => {
    expect(GUEST_SUBMISSION_ERROR_COPY.captcha).toBe("Please complete the verification and try again.");
  });

  it("has the exact rate-limit guidance", () => {
    expect(GUEST_SUBMISSION_ERROR_COPY["rate-limit"]).toBe("Please try again in a few minutes.");
  });

  it("has the exact generic guidance", () => {
    expect(GUEST_SUBMISSION_ERROR_COPY.generic).toBe("Something went wrong. Please try again.");
  });
});
