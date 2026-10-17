import { describe, it, expect, vi } from "vitest";
import { adminRequest, isMfaRequiredError } from "./adminRequest";
import { onMfaRequired } from "./mfaRequiredSignal";
import type { ApiError } from "@/lib/api/ApiError";

vi.mock("@/lib/auth/refreshSession", () => ({
  refreshSession: vi.fn(),
}));

function mfaRequiredError(): ApiError {
  return { kind: "http", status: 401, code: "MFA_REQUIRED", message: "x", raw: undefined };
}

function authRequiredError(): ApiError {
  return { kind: "http", status: 401, code: "AUTH_REQUIRED", message: "x", raw: undefined };
}

describe("isMfaRequiredError", () => {
  it("is true for a 401 MFA_REQUIRED ApiError", () => {
    expect(isMfaRequiredError(mfaRequiredError())).toBe(true);
  });

  it("is false for a 401 AUTH_REQUIRED ApiError", () => {
    expect(isMfaRequiredError(authRequiredError())).toBe(false);
  });

  it("is false for a non-ApiError value", () => {
    expect(isMfaRequiredError(new Error("boom"))).toBe(false);
  });
});

// #PHASE3-ADMIN-REQUEST — every admin data hook wraps its apiClient call
// through this instead of calling authenticatedRequest directly, so the
// MFA_REQUIRED -> "send this admin to MFA setup" rule (P1-1 Notes) is
// handled in exactly one place, not re-implemented per hook.
describe("adminRequest", () => {
  it("resolves with the call's own result on success, without notifying the MFA signal", async () => {
    const listener = vi.fn();
    const unsubscribe = onMfaRequired(listener);

    const result = await adminRequest(async () => "ok");

    expect(result).toBe("ok");
    expect(listener).not.toHaveBeenCalled();
    unsubscribe();
  });

  it("notifies the MFA-required signal and re-throws the original error when the call rejects with MFA_REQUIRED", async () => {
    const listener = vi.fn();
    const unsubscribe = onMfaRequired(listener);

    await expect(adminRequest(() => Promise.reject(mfaRequiredError()))).rejects.toMatchObject({
      code: "MFA_REQUIRED",
    });

    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
  });

  it("re-throws a non-MFA_REQUIRED error without notifying the MFA signal", async () => {
    const listener = vi.fn();
    const unsubscribe = onMfaRequired(listener);

    await expect(adminRequest(() => Promise.reject(authRequiredError()))).rejects.toMatchObject({
      code: "AUTH_REQUIRED",
    });

    expect(listener).not.toHaveBeenCalled();
    unsubscribe();
  });
});
