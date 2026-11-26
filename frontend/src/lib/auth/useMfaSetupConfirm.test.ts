import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { apiClient } from "@/lib/api/apiClient";
import type { ApiError } from "@/lib/api/ApiError";
import { useMfaSetupConfirm } from "./useMfaSetupConfirm";

// P1-2 — finishes MFA enrolment. Only `code` (the TOTP code generated
// from the new secret), plus CSRF. Response is MfaRecoveryCodesRead
// (recovery_codes[], generated_at) — displayed once, the caller owns
// requiring explicit acknowledgment before navigating away.
function createWrapper() {
  const queryClient = new QueryClient();
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

function httpError(status: number, code: string): ApiError {
  return { kind: "http", status, code, message: "x", raw: undefined };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useMfaSetupConfirm", () => {
  it("posts code to the exact path, with csrf: true", async () => {
    const responseBody = { recovery_codes: ["aaaa-bbbb", "cccc-dddd"], generated_at: "2026-01-01T00:00:00Z" };
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(responseBody);
    const { result } = renderHook(() => useMfaSetupConfirm(), { wrapper: createWrapper() });

    const outcome = await act(async () => result.current.mutateAsync({ code: "123456" }));

    expect(outcome).toEqual(responseBody);
    const [path, body, options] = postSpy.mock.calls[0] as [string, unknown, Record<string, unknown> | undefined];
    expect(path).toBe("/api/v1/auth/mfa/setup/confirm");
    expect(body).toEqual({ code: "123456" });
    expect(options?.csrf).toBe(true);
  });

  it("a 422 MFA_INVALID failure passes through unchanged (code doesn't match the new secret)", async () => {
    const error = httpError(422, "MFA_INVALID");
    vi.spyOn(apiClient, "post").mockRejectedValue(error);
    const { result } = renderHook(() => useMfaSetupConfirm(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(result.current.mutateAsync({ code: "000000" })).rejects.toBe(error);
    });
  });

  it("a 409 INVALID_STATE_TRANSITION failure passes through unchanged", async () => {
    const error = httpError(409, "INVALID_STATE_TRANSITION");
    vi.spyOn(apiClient, "post").mockRejectedValue(error);
    const { result } = renderHook(() => useMfaSetupConfirm(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(result.current.mutateAsync({ code: "123456" })).rejects.toBe(error);
    });
  });
});
