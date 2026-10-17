import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { apiClient } from "@/lib/api/apiClient";
import type { ApiError } from "@/lib/api/ApiError";
import { useMfaVerify } from "./useMfaVerify";

// P1-2 — finishes an administrator login. Sends challenge_id plus
// exactly one of code/recovery_code. No cookie exists yet and no CSRF
// header is sent — the challenge_id itself is the credential. Success
// is 204 (no body); the three session cookies arrive via Set-Cookie,
// never read or inspected here.
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

describe("useMfaVerify", () => {
  it("posts challenge_id and code to the exact path, with no csrf option", async () => {
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(undefined);
    const { result } = renderHook(() => useMfaVerify(), { wrapper: createWrapper() });

    await act(async () => {
      await result.current.mutateAsync({ challenge_id: "chal-1", code: "123456" });
    });

    expect(postSpy).toHaveBeenCalledTimes(1);
    const [path, body, options] = postSpy.mock.calls[0] as [string, unknown, Record<string, unknown> | undefined];
    expect(path).toBe("/api/v1/auth/mfa/verify");
    expect(body).toEqual({ challenge_id: "chal-1", code: "123456" });
    expect(options?.csrf).toBeUndefined();
  });

  it("supports recovery_code in place of code", async () => {
    vi.spyOn(apiClient, "post").mockResolvedValue(undefined);
    const { result } = renderHook(() => useMfaVerify(), { wrapper: createWrapper() });

    await act(async () => {
      await result.current.mutateAsync({ challenge_id: "chal-1", recovery_code: "abcd-efgh" });
    });

    const [, body] = vi.mocked(apiClient.post).mock.calls[0] as [string, unknown];
    expect(body).toEqual({ challenge_id: "chal-1", recovery_code: "abcd-efgh" });
  });

  it("a 401 MFA_INVALID failure passes through unchanged (the challenge is burned; caller must re-login)", async () => {
    const error = httpError(401, "MFA_INVALID");
    vi.spyOn(apiClient, "post").mockRejectedValue(error);
    const { result } = renderHook(() => useMfaVerify(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(result.current.mutateAsync({ challenge_id: "chal-1", code: "000000" })).rejects.toBe(error);
    });
  });

  it("a 410 RESOURCE_EXPIRED failure passes through unchanged", async () => {
    const error = httpError(410, "RESOURCE_EXPIRED");
    vi.spyOn(apiClient, "post").mockRejectedValue(error);
    const { result } = renderHook(() => useMfaVerify(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(result.current.mutateAsync({ challenge_id: "chal-1", code: "000000" })).rejects.toBe(error);
    });
  });

  it("retry: false — a rejection is never retried", async () => {
    vi.useFakeTimers();
    const postSpy = vi.spyOn(apiClient, "post").mockRejectedValue(httpError(401, "MFA_INVALID"));
    const { result } = renderHook(() => useMfaVerify(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(result.current.mutateAsync({ challenge_id: "chal-1", code: "000000" })).rejects.toBeDefined();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });

    expect(postSpy).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });
});
