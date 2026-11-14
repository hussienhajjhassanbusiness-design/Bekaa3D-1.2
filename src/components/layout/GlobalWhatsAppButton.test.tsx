import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/apiClient";
import { GlobalWhatsAppButton } from "./GlobalWhatsAppButton";
// Storefront chrome (Batch 9): these tests cover the non-admin case;
// SiteChrome.test.tsx covers the admin switch.
vi.mock("./useAdminChrome", () => ({ useAdminChrome: () => false }));

function renderButton() {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <GlobalWhatsAppButton />
    </QueryClientProvider>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("GlobalWhatsAppButton", () => {
  it("renders the floating button once a WhatsApp number is configured", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      accepting_orders: true,
      cash_payment_enabled: true,
      cash_max_order_total: { amount_cents: 10000, currency: "USD" },
      pickup_address: null,
      pickup_hours: null,
      whatsapp_number: "+96170000000",
    });

    renderButton();

    expect(await screen.findByRole("link", { name: /chat with us on whatsapp/i })).toBeInTheDocument();
  });

  it("renders nothing when no WhatsApp number is configured", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      accepting_orders: true,
      cash_payment_enabled: true,
      cash_max_order_total: { amount_cents: 10000, currency: "USD" },
      pickup_address: null,
      pickup_hours: null,
      whatsapp_number: null,
    });

    renderButton();

    await waitFor(() => expect(apiClient.get).toHaveBeenCalled());
    expect(screen.queryByRole("link", { name: /chat with us on whatsapp/i })).not.toBeInTheDocument();
  });

  it("renders nothing (never a broken link) when the settings fetch fails", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue({ kind: "network", message: "x", raw: undefined });

    renderButton();

    await waitFor(() => expect(apiClient.get).toHaveBeenCalled());
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
