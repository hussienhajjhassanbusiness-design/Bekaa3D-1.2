import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { apiClient } from "@/lib/api/apiClient";
import { usePublicSettings } from "./usePublicSettings";

function createWrapper() {
  const queryClient = new QueryClient();
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("usePublicSettings", () => {
  it("calls GET /api/v1/settings/public and returns the normalized model", async () => {
    const getSpy = vi.spyOn(apiClient, "get").mockResolvedValue({
      accepting_orders: true,
      free_shipping_threshold: null,
      pickup_address: null,
      pickup_hours: null,
      whatsapp_number: "+96170000000",
    });

    const { result } = renderHook(() => usePublicSettings(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getSpy).toHaveBeenCalledWith("/api/v1/settings/public");
    expect(result.current.data).toEqual({ whatsappNumber: "96170000000" });
  });

  it("surfaces a null whatsappNumber when the setting is not configured", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      accepting_orders: true,
      free_shipping_threshold: null,
      pickup_address: null,
      pickup_hours: null,
      whatsapp_number: null,
    });

    const { result } = renderHook(() => usePublicSettings(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({ whatsappNumber: null });
  });
});
