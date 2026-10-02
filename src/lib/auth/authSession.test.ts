import { describe, it, expect, vi, afterEach } from "vitest";
import { apiClient } from "@/lib/api/apiClient";
import type { ApiError } from "@/lib/api/ApiError";
import { bootstrapAuthSession, getAuthSessionQueryOptions, AUTH_SESSION_QUERY_KEY } from "./authSession";
import { refreshSession } from "./refreshSession";

// FVS-003-IMPLEMENTATION-PLAN.md §1/§10 (confirmed BATCH 3A) — the
// bounded, at-most-two-/me-calls bootstrap sequence. `refreshSession` is
// mocked directly here (its own real behavior is proven in
// refreshSession.test.ts) so these tests focus purely on the bootstrap
// decision tree.

vi.mock("./refreshSession", () => ({ refreshSession: vi.fn() }));
const mockedRefreshSession = vi.mocked(refreshSession);

const RAW_USER = {
  id: "u-1",
  email: "ada@example.com",
  role: "customer",
  email_verified: true,
  email_verified_at: "2026-01-01T00:00:00Z",
  created_at: "2025-12-01T00:00:00Z",
};

function httpError(status: number, code?: string): ApiError {
  return { kind: "http", status, code, message: "x", raw: undefined };
}

function clearCsrfCookie() {
  document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/";
}

afterEach(() => {
  vi.restoreAllMocks();
  mockedRefreshSession.mockReset();
  clearCsrfCookie();
});

describe("bootstrapAuthSession", () => {
  it("resolves anonymous (null) and makes zero network requests when no csrf_token cookie exists", async () => {
    clearCsrfCookie();
    const getSpy = vi.spyOn(apiClient, "get");

    const result = await bootstrapAuthSession();

    expect(result).toBeNull();
    expect(getSpy).not.toHaveBeenCalled();
    expect(mockedRefreshSession).not.toHaveBeenCalled();
  });

  it("resolves the mapped user when /me returns 200", async () => {
    document.cookie = "csrf_token=abc";
    vi.spyOn(apiClient, "get").mockResolvedValue(RAW_USER);

    const result = await bootstrapAuthSession();

    expect(result).toEqual({
      id: "u-1",
      email: "ada@example.com",
      role: "customer",
      emailVerified: true,
      emailVerifiedAt: "2026-01-01T00:00:00Z",
      createdAt: "2025-12-01T00:00:00Z",
    });
  });

  it("calls GET /api/v1/me directly (not through authenticatedRequest)", async () => {
    document.cookie = "csrf_token=abc";
    const getSpy = vi.spyOn(apiClient, "get").mockResolvedValue(RAW_USER);

    await bootstrapAuthSession();

    expect(getSpy).toHaveBeenCalledWith("/api/v1/me");
  });

  it("on 401 AUTH_REQUIRED, refreshes once then retries /me once, resolving the user on success", async () => {
    document.cookie = "csrf_token=abc";
    const getSpy = vi
      .spyOn(apiClient, "get")
      .mockRejectedValueOnce(httpError(401, "AUTH_REQUIRED"))
      .mockResolvedValueOnce(RAW_USER);
    mockedRefreshSession.mockResolvedValue(true);

    const result = await bootstrapAuthSession();

    expect(result).toEqual(expect.objectContaining({ id: "u-1" }));
    expect(mockedRefreshSession).toHaveBeenCalledTimes(1);
    expect(getSpy).toHaveBeenCalledTimes(2);
  });

  it("resolves anonymous when the refresh after AUTH_REQUIRED fails — no retry of /me is attempted", async () => {
    document.cookie = "csrf_token=abc";
    const getSpy = vi.spyOn(apiClient, "get").mockRejectedValue(httpError(401, "AUTH_REQUIRED"));
    mockedRefreshSession.mockResolvedValue(false);

    const result = await bootstrapAuthSession();

    expect(result).toBeNull();
    expect(getSpy).toHaveBeenCalledTimes(1);
  });

  it("resolves anonymous when the retried /me is still 401 AUTH_REQUIRED — never loops further", async () => {
    document.cookie = "csrf_token=abc";
    const getSpy = vi.spyOn(apiClient, "get").mockRejectedValue(httpError(401, "AUTH_REQUIRED"));
    mockedRefreshSession.mockResolvedValue(true);

    const result = await bootstrapAuthSession();

    expect(result).toBeNull();
    expect(getSpy).toHaveBeenCalledTimes(2);
    expect(mockedRefreshSession).toHaveBeenCalledTimes(1);
  });

  it("a 401 with a different/unrecognized code resolves anonymous, never authenticated — still a definitive auth signal", async () => {
    document.cookie = "csrf_token=abc";

    vi.spyOn(apiClient, "get").mockRejectedValue(httpError(401, "MFA_REQUIRED"));
    await expect(bootstrapAuthSession()).resolves.toBeNull();

    expect(mockedRefreshSession).not.toHaveBeenCalled();
  });

  // FVS-006-IMPLEMENTATION-PLAN.md T01 — a genuine transport/server failure
  // says NOTHING about whether the current session is valid. Collapsing it
  // into "anonymous" was a real cross-slice defect: it would bounce a
  // customer with a perfectly valid session to /login on a transient
  // network blip or a 500, instead of letting the UI show a retryable
  // error. These three cases must now REJECT (so the TanStack query
  // genuinely errors) rather than resolve null.
  it("re-throws a network failure rather than resolving anonymous", async () => {
    document.cookie = "csrf_token=abc";
    const error = { kind: "network", message: "x", raw: undefined };
    vi.spyOn(apiClient, "get").mockRejectedValue(error);

    await expect(bootstrapAuthSession()).rejects.toBe(error);
    expect(mockedRefreshSession).not.toHaveBeenCalled();
  });

  it("re-throws a timeout failure rather than resolving anonymous", async () => {
    document.cookie = "csrf_token=abc";
    const error = { kind: "timeout", message: "x", raw: undefined };
    vi.spyOn(apiClient, "get").mockRejectedValue(error);

    await expect(bootstrapAuthSession()).rejects.toBe(error);
  });

  it("re-throws a 500 server error rather than resolving anonymous", async () => {
    document.cookie = "csrf_token=abc";
    const error = httpError(500);
    vi.spyOn(apiClient, "get").mockRejectedValue(error);

    await expect(bootstrapAuthSession()).rejects.toBe(error);
  });

  it("re-throws an unparseable (parse) response rather than resolving anonymous", async () => {
    document.cookie = "csrf_token=abc";
    const error = { kind: "parse", message: "x", raw: undefined };
    vi.spyOn(apiClient, "get").mockRejectedValue(error);

    await expect(bootstrapAuthSession()).rejects.toBe(error);
  });

  it("re-throws a transport failure on the post-refresh /me retry too, rather than resolving anonymous", async () => {
    document.cookie = "csrf_token=abc";
    const retryError = httpError(500);
    vi.spyOn(apiClient, "get")
      .mockRejectedValueOnce(httpError(401, "AUTH_REQUIRED"))
      .mockRejectedValueOnce(retryError);
    mockedRefreshSession.mockResolvedValue(true);

    await expect(bootstrapAuthSession()).rejects.toBe(retryError);
  });

  it("still resolves anonymous (not an error) when the post-refresh /me retry is still AUTH_REQUIRED", async () => {
    // Regression guard: the new transport-error re-throw must not change
    // this already-correct, already-tested confirmed-anonymous outcome.
    document.cookie = "csrf_token=abc";
    vi.spyOn(apiClient, "get").mockRejectedValue(httpError(401, "AUTH_REQUIRED"));
    mockedRefreshSession.mockResolvedValue(true);

    await expect(bootstrapAuthSession()).resolves.toBeNull();
  });
});

describe("getAuthSessionQueryOptions", () => {
  it("uses the canonical query key", () => {
    expect(getAuthSessionQueryOptions().queryKey).toEqual(["auth", "session"]);
    expect(AUTH_SESSION_QUERY_KEY).toEqual(["auth", "session"]);
  });

  it("configures staleTime: Infinity and retry: false", () => {
    const options = getAuthSessionQueryOptions();
    expect(options.staleTime).toBe(Infinity);
    expect(options.retry).toBe(false);
  });
});
