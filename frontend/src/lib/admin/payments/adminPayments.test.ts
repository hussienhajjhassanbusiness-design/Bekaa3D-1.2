import { describe, it, expect, vi, afterEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { apiClient } from "@/lib/api/apiClient";
import { refreshSession } from "@/lib/auth/refreshSession";
import { adminOrderKeys } from "@/lib/admin/orders/adminOrdersApi";
import { adminPaymentKeys, adminPaymentsApi } from "./adminPaymentsApi";
import {
  ADMIN_PAYMENT_MESSAGES,
  describeAdminPaymentError,
  describePaymentHistoryAction,
  readAvailableBalances,
  refundActions,
} from "./adminPaymentPresentation";
import { createRefundAttemptTracker } from "./refundIdempotency";
import { useAdminFinancialWrite } from "./useAdminPayments";
import { refundDTO } from "./adminPaymentFixtures";

vi.mock("@/lib/auth/refreshSession", () => ({ refreshSession: vi.fn() }));
vi.mock("@/lib/admin/mfaRequiredSignal", () => ({ notifyMfaRequired: vi.fn() }));

const ID = "11111111-1111-4111-8111-111111111111";
const http = (status: number, code: string, extra: Record<string, unknown> = {}) => ({
  kind: "http" as const,
  status,
  code,
  message: "RAW",
  detail: "RAW DETAIL",
  raw: { status, code, ...extra },
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.mocked(refreshSession).mockReset();
});

describe("adminPaymentsApi", () => {
  it("reads payments and refunds with only the backend's filters", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({});
    await adminPaymentsApi.listPayments({ status: "paid", provider: "mock", late_captured: true });
    await adminPaymentsApi.listPayments({});
    await adminPaymentsApi.getPayment(ID);
    await adminPaymentsApi.listRefunds({ queue: false, kind: "cancellation" });
    await adminPaymentsApi.getRefund("r-1");
    expect(get.mock.calls.map((c) => c[0])).toEqual([
      "/api/v1/admin/payments?status=paid&provider=mock&late_captured=true",
      "/api/v1/admin/payments",
      `/api/v1/admin/payments/${ID}`,
      "/api/v1/admin/refunds?queue=false&kind=cancellation",
      "/api/v1/admin/refunds/r-1",
    ]);
  });

  it("financial writes send CSRF; create and reissue send the Idempotency-Key; bodies exact", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({});
    await adminPaymentsApi.createRefund(ID, { items: [{ order_item_id: "l-1", amount_cents: 500 }], reason: "Damaged" }, "key-0000001");
    await adminPaymentsApi.reissueRefund("r-1", "key-0000002");
    await adminPaymentsApi.settleRefund("r-1", { reference: "DASH-1" });
    await adminPaymentsApi.failRefund("r-1", { reason: "Bounced" });
    await adminPaymentsApi.voidRefund("r-1", { reason: "Mistake" });
    await adminPaymentsApi.reconcilePayment(ID);
    expect(post.mock.calls).toEqual([
      [`/api/v1/admin/orders/${ID}/refunds`, { items: [{ order_item_id: "l-1", amount_cents: 500 }], reason: "Damaged" }, { csrf: true, headers: { "Idempotency-Key": "key-0000001" } }],
      ["/api/v1/admin/refunds/r-1/reissue", undefined, { csrf: true, headers: { "Idempotency-Key": "key-0000002" } }],
      ["/api/v1/admin/refunds/r-1/settle", { reference: "DASH-1" }, { csrf: true }],
      ["/api/v1/admin/refunds/r-1/fail", { reason: "Bounced" }, { csrf: true }],
      ["/api/v1/admin/refunds/r-1/void", { reason: "Mistake" }, { csrf: true }],
      [`/api/v1/admin/payments/${ID}/reconcile`, undefined, { csrf: true }],
    ]);
  });

  it("a silent refresh resends the identical keyed request", async () => {
    vi.mocked(refreshSession).mockResolvedValue(true);
    const post = vi.spyOn(apiClient, "post").mockRejectedValueOnce(http(401, "AUTH_REQUIRED")).mockResolvedValueOnce({});
    await adminPaymentsApi.createRefund(ID, { items: [{ order_item_id: "l-1", amount_cents: 5 }], reason: "x" }, "key-0000003");
    expect(post).toHaveBeenCalledTimes(2);
    expect(post.mock.calls[1]).toEqual(post.mock.calls[0]);
  });
});

describe("presentation", () => {
  it("offers refund actions from the documented state machine", () => {
    expect(refundActions(refundDTO())).toEqual(["settle", "fail", "void"]);
    expect(refundActions(refundDTO({ status: "failed", owed: true }))).toEqual(["reissue", "void"]);
    expect(refundActions(refundDTO({ status: "failed", owed: false, reissued_by_refund_id: "r-2" }))).toEqual([]);
    expect(refundActions(refundDTO({ status: "settled" }))).toEqual([]);
    expect(refundActions(refundDTO({ status: "voided" }))).toEqual([]);
  });

  it("maps every documented code; uncertain outcomes keep the key", () => {
    expect(describeAdminPaymentError(http(409, "INVALID_STATE_TRANSITION", { reason: "already_settled" })).message).toMatch(/already settled/);
    expect(describeAdminPaymentError(http(422, "REFUND_EXCEEDS_AVAILABLE")).message).toBe(ADMIN_PAYMENT_MESSAGES.exceeds);
    expect(describeAdminPaymentError(http(422, "REFUND_REQUIRES_CANCELLATION")).message).toBe(ADMIN_PAYMENT_MESSAGES.requiresCancellation);
    expect(describeAdminPaymentError(http(409, "ORDER_NOT_PAID")).message).toBe(ADMIN_PAYMENT_MESSAGES.orderNotPaid);
    expect(describeAdminPaymentError(http(409, "IDEMPOTENCY_REQUEST_IN_PROGRESS")).uncertain).toBe(true);
    expect(describeAdminPaymentError(http(409, "IDEMPOTENCY_KEY_CONFLICT")).uncertain).toBe(false);
    expect(describeAdminPaymentError({ kind: "timeout", message: "x", raw: null })).toEqual({ message: ADMIN_PAYMENT_MESSAGES.uncertain, refetch: true, uncertain: true });
    expect(describeAdminPaymentError(http(503, "PAYMENT_VERIFICATION_UNAVAILABLE")).message).toBe(ADMIN_PAYMENT_MESSAGES.verificationUnavailable);
    expect(describeAdminPaymentError(http(403, "CSRF_INVALID")).message).toBe(ADMIN_PAYMENT_MESSAGES.csrf);
    expect(describeAdminPaymentError(http(418, "X")).message).not.toMatch(/RAW/);
    expect(describePaymentHistoryAction("payment.verified")).toBe("Verified as paid");
    expect(describePaymentHistoryAction("payment.zzz")).toBe("Recorded action");
  });

  it("reads the typed `available` balances, dropping malformed entries", () => {
    expect(readAvailableBalances(http(422, "REFUND_EXCEEDS_AVAILABLE", { available: { lines: [{ order_item_id: "l-1", balance_cents: 900 }, { bad: 1 }], payment_cents: 900 } }))).toEqual({ "l-1": 900 });
    expect(readAvailableBalances(http(422, "REFUND_EXCEEDS_AVAILABLE", { available: "x" }))).toBeNull();
  });
});

describe("refund idempotency + useAdminFinancialWrite", () => {
  it("binds one key to one exact refund; a changed body gets a new key", () => {
    let n = 0;
    const tracker = createRefundAttemptTracker(() => `refund-key-${++n}`);
    expect(tracker.keyFor("a")).toBe("refund-key-1");
    expect(tracker.keyFor("a")).toBe("refund-key-1");
    expect(tracker.keyFor("b")).toBe("refund-key-2");
    tracker.retire();
    expect(tracker.keyFor("b")).toBe("refund-key-3");
  });

  function setup() {
    const queryClient = new QueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const wrapper = ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client: queryClient }, children);
    return { ...renderHook(() => useAdminFinancialWrite(), { wrapper }), queryClient, invalidate };
  }

  it("success: stores the refund, re-reads payments, refunds and orders, retires the key", async () => {
    const { result, queryClient, invalidate } = setup();
    const tracker = { keyFor: vi.fn(), retire: vi.fn() };
    const r = refundDTO();
    await act(async () => {
      await result.current.run(() => Promise.resolve(r), tracker);
    });
    expect(queryClient.getQueryData(adminPaymentKeys.refund("r-1"))).toBe(r);
    expect(invalidate.mock.calls.map((c) => c[0])).toEqual([
      { queryKey: adminPaymentKeys.payments },
      { queryKey: adminPaymentKeys.refunds },
      { queryKey: adminOrderKeys.root },
    ]);
    expect(tracker.retire).toHaveBeenCalledTimes(1);
  });

  it("uncertain outcome keeps the key; a definitive refusal retires it; double submit dropped", async () => {
    const { result } = setup();
    const tracker = { keyFor: vi.fn(), retire: vi.fn() };
    await act(async () => {
      await result.current.run(() => Promise.reject({ kind: "network", message: "x", raw: null }), tracker);
    });
    expect(tracker.retire).not.toHaveBeenCalled();
    await act(async () => {
      await result.current.run(() => Promise.reject(http(422, "REFUND_EXCEEDS_AVAILABLE")), tracker);
    });
    expect(tracker.retire).toHaveBeenCalledTimes(1);

    let resolve: (v: unknown) => void = () => {};
    const call = vi.fn(() => new Promise((r) => (resolve = r)));
    let second: unknown = "x";
    let first: Promise<unknown> = Promise.resolve();
    await act(async () => {
      first = result.current.run(call);
      second = await result.current.run(call);
    });
    expect(second).toBeNull();
    await act(async () => {
      resolve({});
      await first;
    });
    expect(call).toHaveBeenCalledTimes(1);
  });
});
