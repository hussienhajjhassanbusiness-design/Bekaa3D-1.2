import { describe, it, expect, vi, afterEach } from "vitest";
import { apiClient } from "@/lib/api/apiClient";
import { refreshSession } from "@/lib/auth/refreshSession";
import { notificationsApi, buildNotificationsSearchParams } from "./notificationsApi";

// Phase 2 auth/account batch — confirmed wire contract (openapi.json
// paths./api/v1/me/notifications): cursor-paginated, newest first, scoped
// to the caller; `read` is an optional boolean query filter. The exact
// query-param names below are a direct quote of the real parameters —
// this is the one place that builds a /me/notifications request by hand.

vi.mock("@/lib/auth/refreshSession", () => ({ refreshSession: vi.fn() }));
const mockedRefreshSession = vi.mocked(refreshSession);

afterEach(() => {
  vi.restoreAllMocks();
});

describe("buildNotificationsSearchParams", () => {
  it("builds an empty querystring for no params", () => {
    expect(buildNotificationsSearchParams({}).toString()).toBe("");
  });

  it("passes cursor/limit/read through unchanged", () => {
    const search = buildNotificationsSearchParams({ cursor: "opaque-cursor", limit: 10, read: false });
    expect(search.get("cursor")).toBe("opaque-cursor");
    expect(search.get("limit")).toBe("10");
    expect(search.get("read")).toBe("false");
  });

  it("omits read when undefined (never defaults to a filter)", () => {
    expect(buildNotificationsSearchParams({}).has("read")).toBe(false);
  });
});

describe("notificationsApi.listNotifications", () => {
  it("calls GET /api/v1/me/notifications with the built querystring", async () => {
    const getSpy = vi.spyOn(apiClient, "get").mockResolvedValue({ items: [], next_cursor: null });

    await notificationsApi.listNotifications({ limit: 20 });

    expect(getSpy).toHaveBeenCalledWith("/api/v1/me/notifications?limit=20");
  });

  it("calls the bare path when there are no params", async () => {
    const getSpy = vi.spyOn(apiClient, "get").mockResolvedValue({ items: [], next_cursor: null });

    await notificationsApi.listNotifications({});

    expect(getSpy).toHaveBeenCalledWith("/api/v1/me/notifications");
  });

  it("is wrapped in authenticatedRequest — a 401 AUTH_REQUIRED triggers exactly one refresh, then retries", async () => {
    mockedRefreshSession.mockResolvedValue(true);
    const authRequiredError = { kind: "http" as const, status: 401, code: "AUTH_REQUIRED", message: "x", raw: {} };
    const getSpy = vi
      .spyOn(apiClient, "get")
      .mockRejectedValueOnce(authRequiredError)
      .mockResolvedValueOnce({ items: [], next_cursor: null });

    const result = await notificationsApi.listNotifications({});

    expect(result).toEqual({ items: [], next_cursor: null });
    expect(getSpy).toHaveBeenCalledTimes(2);
    expect(mockedRefreshSession).toHaveBeenCalledTimes(1);
  });
});

describe("notificationsApi.setNotificationRead", () => {
  it("calls PATCH /api/v1/me/notifications/{id} with { read } and csrf: true", async () => {
    const patchSpy = vi
      .spyOn(apiClient, "patch")
      .mockResolvedValue({ id: "n1", type: "account", payload: {}, read: true, created_at: "2026-01-01T00:00:00Z" });

    await notificationsApi.setNotificationRead("n1", true);

    expect(patchSpy).toHaveBeenCalledWith("/api/v1/me/notifications/n1", { read: true }, { csrf: true });
  });

  it("is wrapped in authenticatedRequest — a 401 AUTH_REQUIRED triggers exactly one refresh, then retries", async () => {
    mockedRefreshSession.mockResolvedValue(true);
    const authRequiredError = { kind: "http" as const, status: 401, code: "AUTH_REQUIRED", message: "x", raw: {} };
    const patchSpy = vi
      .spyOn(apiClient, "patch")
      .mockRejectedValueOnce(authRequiredError)
      .mockResolvedValueOnce({ id: "n1", type: "account", payload: {}, read: true, created_at: "2026-01-01T00:00:00Z" });

    const result = await notificationsApi.setNotificationRead("n1", true);

    expect(result.read).toBe(true);
    expect(patchSpy).toHaveBeenCalledTimes(2);
  });
});
