import { describe, it, expect, vi, afterEach } from "vitest";
import { apiClient } from "@/lib/api/apiClient";
import { refreshSession } from "@/lib/auth/refreshSession";
import { notifyMfaRequired } from "@/lib/admin/mfaRequiredSignal";
import { adminOrderKeys, adminOrdersApi, buildAdminOrdersSearchParams } from "./adminOrdersApi";

vi.mock("@/lib/auth/refreshSession", () => ({ refreshSession: vi.fn() }));
vi.mock("@/lib/admin/mfaRequiredSignal", () => ({ notifyMfaRequired: vi.fn() }));
const mockedRefresh = vi.mocked(refreshSession);

const ID = "11111111-1111-4111-8111-111111111111";
const ITEM = "22222222-2222-4222-8222-222222222222";

afterEach(() => {
  vi.restoreAllMocks();
  mockedRefresh.mockReset();
  vi.mocked(notifyMfaRequired).mockReset();
});

describe("buildAdminOrdersSearchParams", () => {
  it("sends only the backend's own filter names, omitting unset ones", () => {
    expect(buildAdminOrdersSearchParams({}).toString()).toBe("");
    const s = buildAdminOrdersSearchParams({
      status: "in_progress",
      fulfillment_method: "pickup",
      payment_method: "cash",
      payment_due: true,
      order_number: "B3D-1",
      cursor: "c",
      limit: 25,
    });
    expect(Object.fromEntries(s)).toEqual({
      status: "in_progress",
      fulfillment_method: "pickup",
      payment_method: "cash",
      payment_due: "true",
      order_number: "B3D-1",
      cursor: "c",
      limit: "25",
    });
  });
});

describe("adminOrdersApi", () => {
  it("reads the queue and one order", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({});
    await adminOrdersApi.listOrders({ payment_due: true });
    await adminOrdersApi.listOrders({});
    await adminOrdersApi.getOrder(ID);
    expect(get.mock.calls.map((c) => c[0])).toEqual([
      "/api/v1/admin/orders?payment_due=true",
      "/api/v1/admin/orders",
      `/api/v1/admin/orders/${ID}`,
    ]);
  });

  it("transitions one line with CSRF and exactly the request body", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({});
    await adminOrdersApi.transitionLine(ID, ITEM, { target_status: "cancelled", cancel_reason: "refused", reason: "Customer refused" });
    expect(post).toHaveBeenCalledWith(
      `/api/v1/admin/orders/${ID}/items/${ITEM}/transition`,
      { target_status: "cancelled", cancel_reason: "refused", reason: "Customer refused" },
      { csrf: true }
    );
  });

  it("records a cash handover, cancels an order, sets the note — all with CSRF", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({});
    const patch = vi.spyOn(apiClient, "patch").mockResolvedValue({});
    await adminOrdersApi.cashHandover(ID, { amount_cents: 3600, currency: "USD" });
    await adminOrdersApi.cancelOrder(ID, { reason: "Out of stock" });
    await adminOrdersApi.updateNote(ID, { admin_note: null });
    expect(post.mock.calls).toEqual([
      [`/api/v1/admin/orders/${ID}/cash-handover`, { amount_cents: 3600, currency: "USD" }, { csrf: true }],
      [`/api/v1/admin/orders/${ID}/cancel`, { reason: "Out of stock" }, { csrf: true }],
    ]);
    expect(patch).toHaveBeenCalledWith(`/api/v1/admin/orders/${ID}`, { admin_note: null }, { csrf: true });
  });

  it("reads the STL delivery queue", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({});
    await adminOrdersApi.listStlDeliveries({});
    await adminOrdersApi.listStlDeliveries({ cursor: "abc", limit: 50 });
    expect(get.mock.calls.map((c) => c[0])).toEqual([
      "/api/v1/admin/stl-deliveries",
      "/api/v1/admin/stl-deliveries?cursor=abc&limit=50",
    ]);
  });

  it("signals MFA_REQUIRED and never retries a write's refusal", async () => {
    const mfa = { kind: "http" as const, status: 401, code: "MFA_REQUIRED", message: "x", raw: {} };
    const post = vi.spyOn(apiClient, "post").mockRejectedValue(mfa);
    await expect(adminOrdersApi.cashHandover(ID, { amount_cents: 1, currency: "USD" })).rejects.toBe(mfa);
    expect(notifyMfaRequired).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledTimes(1);
    expect(mockedRefresh).not.toHaveBeenCalled();
  });

  it("refreshes once on AUTH_REQUIRED and resends the identical write", async () => {
    mockedRefresh.mockResolvedValue(true);
    const auth = { kind: "http" as const, status: 401, code: "AUTH_REQUIRED", message: "x", raw: {} };
    const post = vi.spyOn(apiClient, "post").mockRejectedValueOnce(auth).mockResolvedValueOnce({ id: ID });
    await adminOrdersApi.transitionLine(ID, ITEM, { target_status: "shipped" });
    expect(post).toHaveBeenCalledTimes(2);
    expect(post.mock.calls[1]).toEqual(post.mock.calls[0]);
  });
});

describe("adminOrderKeys", () => {
  it("hangs every key off the user-scoped ['admin'] root", () => {
    expect(adminOrderKeys.root).toEqual(["admin", "orders"]);
    expect(adminOrderKeys.detail(ID)).toEqual(["admin", "orders", "detail", ID]);
    expect(adminOrderKeys.list({}).slice(0, 3)).toEqual(adminOrderKeys.lists());
    expect(adminOrderKeys.stl({})[2]).toBe("stl-deliveries");
  });
});
