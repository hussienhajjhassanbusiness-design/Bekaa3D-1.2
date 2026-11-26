import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { apiClient } from "@/lib/api/apiClient";
import type { ApiError } from "@/lib/api/ApiError";
import { useMfaSetup } from "./useMfaSetup";

// P1-2 — begins MFA enrolment. Requires current_password + CSRF (the
// admin already has a session at this point). Response carries
// secret/otpauth_uri/issuer/account_name — all sensitive, memory-only;
// this hook makes no claim about storage, it only shapes the request.
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

describe("useMfaSetup", () => {
  it("posts current_password to the exact path, with csrf: true", async () => {
    const responseBody = {
      secret: "SECRET123",
      otpauth_uri: "otpauth://totp/Bekaa3D:admin@example.com?secret=SECRET123",
      issuer: "Bekaa3D",
      account_name: "admin@example.com",
    };
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(responseBody);
    const { result } = renderHook(() => useMfaSetup(), { wrapper: createWrapper() });

    const outcome = await act(async () => result.current.mutateAsync({ current_password: "hunter2" }));

    expect(outcome).toEqual(responseBody);
    const [path, body, options] = postSpy.mock.calls[0] as [string, unknown, Record<string, unknown> | undefined];
    expect(path).toBe("/api/v1/auth/mfa/setup");
    expect(body).toEqual({ current_password: "hunter2" });
    expect(options?.csrf).toBe(true);
  });

  it("a 401 INVALID_CREDENTIALS failure passes through unchanged", async () => {
    const error = httpError(401, "INVALID_CREDENTIALS");
    vi.spyOn(apiClient, "post").mockRejectedValue(error);
    const { result } = renderHook(() => useMfaSetup(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(result.current.mutateAsync({ current_password: "wrong" })).rejects.toBe(error);
    });
  });

  it("a 409 INVALID_STATE_TRANSITION failure passes through unchanged (MFA already enabled)", async () => {
    const error = httpError(409, "INVALID_STATE_TRANSITION");
    vi.spyOn(apiClient, "post").mockRejectedValue(error);
    const { result } = renderHook(() => useMfaSetup(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(result.current.mutateAsync({ current_password: "hunter2" })).rejects.toBe(error);
    });
  });

  it("retry: false — a rejection is never retried", async () => {
    vi.useFakeTimers();
    const postSpy = vi.spyOn(apiClient, "post").mockRejectedValue(httpError(401, "INVALID_CREDENTIALS"));
    const { result } = renderHook(() => useMfaSetup(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(result.current.mutateAsync({ current_password: "wrong" })).rejects.toBeDefined();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });

    expect(postSpy).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });
});
