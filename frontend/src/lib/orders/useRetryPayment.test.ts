import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { ordersApi } from "./ordersApi";
import { orderKeys } from "./orderKeys";
import { useRetryPayment } from "./useRetryPayment";
import { ORDER_ID } from "./orderFixtures";
import { followPaymentRedirect } from "@/lib/checkout/paymentRedirect";
import { IDEMPOTENCY_KEY_PATTERN } from "@/lib/checkout/checkoutIdempotency";
import type { PaymentRetryReadDTO } from "./orderTypes";

vi.mock("@/lib/checkout/paymentRedirect", () => ({ followPaymentRedirect: vi.fn() }));
const mockedFollow = vi.mocked(followPaymentRedirect);

const REDIRECT = "http://localhost:3000/checkout/return?order=B3D-2026-000123";

function read(redirect: string | null = REDIRECT): PaymentRetryReadDTO {
  return {
    order: {
      id: ORDER_ID,
      order_number: "B3D-2026-000123",
      status: "pending_payment",
      total_cents: 2500,
      currency: "USD",
      hold_expires_at: "2026-11-10T10:30:00Z",
    },
    payment: { id: "p-2", status: "pending", provider: "mock", amount_cents: 2500, currency: "USD", redirect_url: redirect },
  };
}

const http = (status: number, code: string, extra: Record<string, unknown> = {}) => ({
  kind: "http" as const,
  status,
  code,
  message: "RAW",
  detail: "RAW DETAIL",
  raw: { status, code, ...extra },
});

function setup() {
  const queryClient = new QueryClient();
  const invalidate = vi.spyOn(queryClient, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
  const hook = renderHook(() => useRetryPayment(ORDER_ID), { wrapper });
  return { ...hook, invalidate };
}

beforeEach(() => {
  mockedFollow.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useRetryPayment", () => {
  it("posts with a backend-valid key, follows the server's redirect_url exactly, and re-reads the order family", async () => {
    const spy = vi.spyOn(ordersApi, "retryPayment").mockResolvedValue(read());
    const { result, invalidate } = setup();
    await act(() => result.current.start());
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy.mock.calls[0]![0]).toBe(ORDER_ID);
    expect(spy.mock.calls[0]![1]).toMatch(IDEMPOTENCY_KEY_PATTERN);
    expect(mockedFollow).toHaveBeenCalledWith(REDIRECT);
    expect(result.current.state.kind).toBe("redirecting");
    expect(invalidate).toHaveBeenCalledWith({ queryKey: orderKeys.root });
  });

  it.each(["javascript:alert(1)", "data:text/html,x", "/checkout/return", null])(
    "never follows an unsafe or missing redirect (%s); the order is re-read instead",
    async (redirect) => {
      vi.spyOn(ordersApi, "retryPayment").mockResolvedValue(read(redirect));
      const { result, invalidate } = setup();
      await act(() => result.current.start());
      expect(mockedFollow).not.toHaveBeenCalled();
      expect(result.current.state.kind).toBe("started");
      expect(invalidate).toHaveBeenCalledWith({ queryKey: orderKeys.root });
    }
  );

  it("a double press sends ONE request", async () => {
    let resolve!: (value: PaymentRetryReadDTO) => void;
    const spy = vi
      .spyOn(ordersApi, "retryPayment")
      .mockReturnValue(new Promise<PaymentRetryReadDTO>((r) => (resolve = r)));
    const { result } = setup();
    let first!: Promise<void>;
    act(() => {
      first = result.current.start();
      void result.current.start();
    });
    expect(result.current.state.kind).toBe("sending");
    await act(async () => {
      resolve(read());
      await first;
    });
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("an uncertain outcome keeps the key: the resend uses the SAME key", async () => {
    const spy = vi
      .spyOn(ordersApi, "retryPayment")
      .mockRejectedValueOnce({ kind: "timeout", message: "x", raw: undefined })
      .mockRejectedValueOnce(http(409, "IDEMPOTENCY_REQUEST_IN_PROGRESS"))
      .mockResolvedValueOnce(read());
    const { result } = setup();
    await act(() => result.current.start());
    expect(result.current.state).toMatchObject({ kind: "error", outcome: { uncertain: true } });
    await act(() => result.current.start());
    await act(() => result.current.start());
    const keys = spy.mock.calls.map((call) => call[1]);
    expect(new Set(keys).size).toBe(1);
    expect(mockedFollow).toHaveBeenCalledTimes(1);
  });

  it("a definitive answer retires the key: the next press is a new attempt with a NEW key", async () => {
    const spy = vi
      .spyOn(ordersApi, "retryPayment")
      .mockRejectedValueOnce(http(502, "PAYMENT_PROVIDER_UNAVAILABLE", { order_id: ORDER_ID }))
      .mockResolvedValueOnce(read(null))
      .mockResolvedValueOnce(read(null));
    const { result } = setup();
    await act(() => result.current.start());
    expect(result.current.state).toMatchObject({ kind: "error", outcome: { kind: "provider-unavailable" } });
    await act(() => result.current.start());
    await act(() => result.current.start());
    const keys = spy.mock.calls.map((call) => call[1]);
    expect(new Set(keys).size).toBe(3);
  });

  it("a refusal re-reads the canonical order (the server's state explains it)", async () => {
    vi.spyOn(ordersApi, "retryPayment").mockRejectedValue(
      http(409, "INVALID_STATE_TRANSITION", { reason: "checkout_hold_expired" })
    );
    const { result, invalidate } = setup();
    await act(() => result.current.start());
    expect(result.current.state).toMatchObject({ kind: "error", outcome: { kind: "not-retryable" } });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: orderKeys.root });
    expect(mockedFollow).not.toHaveBeenCalled();
  });

  it("PAYMENT_ALREADY_ACTIVE offers the live attempt; resume follows it only on the customer's press", async () => {
    const url = "https://pay.example.test/s/1";
    vi.spyOn(ordersApi, "retryPayment").mockRejectedValue(
      http(409, "PAYMENT_ALREADY_ACTIVE", { payment_status: "pending", redirect_url: url })
    );
    const { result } = setup();
    await act(() => result.current.start());
    expect(mockedFollow).not.toHaveBeenCalled();
    expect(result.current.state).toMatchObject({ kind: "error", outcome: { resumeUrl: url } });
    act(() => result.current.resume(url));
    expect(mockedFollow).toHaveBeenCalledWith(url);
    expect(result.current.state.kind).toBe("redirecting");
  });

  it("resume refuses an unsafe URL", () => {
    const { result } = setup();
    act(() => result.current.resume("javascript:alert(1)"));
    expect(mockedFollow).not.toHaveBeenCalled();
  });

  it("CSRF failure is a safe, definitive message with no redirect", async () => {
    vi.spyOn(ordersApi, "retryPayment").mockRejectedValue(http(403, "CSRF_INVALID"));
    const { result } = setup();
    await act(() => result.current.start());
    expect(result.current.state).toMatchObject({
      kind: "error",
      outcome: { message: "Unable to verify your session. Please refresh the page and try again." },
    });
  });
});
