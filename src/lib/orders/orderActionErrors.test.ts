import { describe, it, expect } from "vitest";
import { describeOrderActionError, ORDER_ACTION_MESSAGES as M } from "./orderActionErrors";

const http = (status: number, code: string, extra: Record<string, unknown> = {}, retryAfterSeconds?: number) => ({
  kind: "http" as const,
  status,
  code,
  message: "RAW MESSAGE",
  detail: "RAW DETAIL",
  retryAfterSeconds,
  raw: { status, code, detail: "RAW DETAIL", ...extra },
});

describe("describeOrderActionError", () => {
  it("maps 409 ORDER_NOT_CANCELLABLE to frontend copy and asks for a re-read", () => {
    const o = describeOrderActionError("cancel", http(409, "ORDER_NOT_CANCELLABLE"));
    expect(o).toEqual({ kind: "refused", message: M.notCancellable, refetchOrder: true });
  });

  it("maps 409 INVALID_STATE_TRANSITION no_delivered_line for both receipt actions", () => {
    const err = http(409, "INVALID_STATE_TRANSITION", { reason: "no_delivered_line" });
    expect(describeOrderActionError("confirm-receipt", err)).toEqual({
      kind: "refused",
      message: M.noDeliveredLine,
      refetchOrder: true,
    });
    expect(describeOrderActionError("report-problem", err).message).toBe(M.noDeliveredLine);
  });

  it("an unknown INVALID_STATE_TRANSITION reason still gets safe copy", () => {
    const o = describeOrderActionError("confirm-receipt", http(409, "INVALID_STATE_TRANSITION", { reason: "zzz" }));
    expect(o.message).toBe(M.stateChanged);
    expect(o.refetchOrder).toBe(true);
  });

  it("hides foreign vs unknown orders behind one not-found message", () => {
    const o = describeOrderActionError("cancel", http(404, "NOT_FOUND"));
    expect(o).toEqual({ kind: "not-found", message: M.notFound, refetchOrder: true });
  });

  it("CSRF (server or missing-cookie local precondition), session, verified email", () => {
    expect(describeOrderActionError("cancel", http(403, "CSRF_INVALID")).message).toBe(M.csrf);
    expect(describeOrderActionError("cancel", { kind: "csrf", message: "x", raw: null }).message).toBe(M.csrf);
    expect(describeOrderActionError("cancel", http(401, "AUTH_REQUIRED"))).toEqual({
      kind: "session-expired",
      message: M.sessionExpired,
      refetchOrder: false,
    });
    expect(describeOrderActionError("report-problem", http(403, "EMAIL_VERIFICATION_REQUIRED"))).toEqual({
      kind: "verify-email",
      message: M.verifyEmail,
      refetchOrder: false,
    });
  });

  it("422 on a report is a message problem; on another action it is generic", () => {
    expect(describeOrderActionError("report-problem", http(422, "VALIDATION_ERROR")).message).toBe(M.invalidMessage);
    expect(describeOrderActionError("cancel", http(422, "VALIDATION_ERROR")).message).toBe(M.generic.cancel);
  });

  it("429 uses Retry-After when present", () => {
    expect(describeOrderActionError("cancel", http(429, "RATE_LIMITED", {}, 120)).message).toBe(
      "Too many requests. Please try again in 2 minutes."
    );
    expect(describeOrderActionError("report-problem", http(429, "RATE_LIMITED")).message).toBe(M.rateLimited);
  });

  it("network, timeout and 5xx: outcome unknown, re-read the order, safe copy", () => {
    for (const err of [
      { kind: "network" as const, message: "x", raw: null },
      { kind: "timeout" as const, message: "x", raw: null },
      http(500, "INTERNAL_ERROR"),
    ]) {
      expect(describeOrderActionError("cancel", err)).toEqual({
        kind: "uncertain",
        message: M.uncertain,
        refetchOrder: true,
      });
    }
  });

  it("never returns backend text", () => {
    const all = [
      describeOrderActionError("cancel", http(409, "ORDER_NOT_CANCELLABLE")),
      describeOrderActionError("report-problem", http(422, "VALIDATION_ERROR")),
      describeOrderActionError("cancel", http(418, "TEAPOT")),
      describeOrderActionError("cancel", new Error("RAW")),
    ];
    for (const o of all) {
      expect(o.message).not.toMatch(/RAW/);
    }
  });
});
