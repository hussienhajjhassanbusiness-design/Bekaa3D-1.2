import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { apiClient } from "@/lib/api/apiClient";
import type { ApiError } from "@/lib/api/ApiError";
import { useMfaRecoveryRegenerate } from "./useMfaRecoveryRegenerate";

// P1-2 — invalidates all existing recovery codes and issues ten new
// ones, requiring current_password + CSRF, mirroring useMfaSetup's
// shape exactly (same request schema).
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

describe("useMfaRecoveryRegenerate", () => {
  it("posts current_password to the exact path, with csrf: true", async () => {
    const responseBody = { recovery_codes: ["eeee-ffff"], generated_at: "2026-01-02T00:00:00Z" };
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(responseBody);
    const { result } = renderHook(() => useMfaRecoveryRegenerate(), { wrapper: createWrapper() });

    const outcome = await act(async () => result.current.mutateAsync({ current_password: "hunter2" }));

    expect(outcome).toEqual(responseBody);
    const [path, body, options] = postSpy.mock.calls[0] as [string, unknown, Record<string, unknown> | undefined];
    expect(path).toBe("/api/v1/auth/mfa/recovery-codes/regenerate");
    expect(body).toEqual({ current_password: "hunter2" });
    expect(options?.csrf).toBe(true);
  });

  it("a 401 INVALID_CREDENTIALS failure passes through unchanged", async () => {
    const error = httpError(401, "INVALID_CREDENTIALS");
    vi.spyOn(apiClient, "post").mockRejectedValue(error);
    const { result } = renderHook(() => useMfaRecoveryRegenerate(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(result.current.mutateAsync({ current_password: "wrong" })).rejects.toBe(error);
    });
  });
});
