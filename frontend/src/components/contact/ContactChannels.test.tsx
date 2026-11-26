import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/apiClient";
import { ContactChannels } from "./ContactChannels";

// Redesign Batch 8 — the Contact aside shows only real information: the email
// reply channel always, and WhatsApp / pickup rows only when configured in
// public settings. Never a guessed address, phone, hours or social link.

function settings(overrides: Record<string, unknown> = {}) {
  return {
    accepting_orders: true,
    cash_payment_enabled: true,
    cash_max_order_total: { amount_cents: 10000, currency: "USD" },
    pickup_address: null,
    pickup_hours: null,
    whatsapp_number: null,
    ...overrides,
  };
}

function renderChannels() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ContactChannels />
    </QueryClientProvider>
  );
}

afterEach(() => vi.restoreAllMocks());

describe("ContactChannels", () => {
  it("renders configured WhatsApp and pickup rows from public settings", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue(
      settings({ whatsapp_number: "+96170000000", pickup_address: "Main Street, Zahle", pickup_hours: "Mon–Fri 9–5" })
    );
    renderChannels();
    const region = screen.getByRole("region", { name: "Other ways to reach us" });
    const link = await within(region).findByRole("link", { name: /chat with us on whatsapp/i });
    expect(link).toHaveAttribute("href", expect.stringContaining("wa.me/96170000000"));
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(within(region).getByText("Main Street, Zahle")).toBeInTheDocument();
    expect(within(region).getByText("Mon–Fri 9–5")).toBeInTheDocument();
  });

  it("shows only the email reply channel when nothing is configured", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue(settings());
    renderChannels();
    await vi.waitFor(() => expect(get).toHaveBeenCalled());
    const region = screen.getByRole("region", { name: "Other ways to reach us" });
    expect(within(region).getByText(/we answer every message by email/i)).toBeInTheDocument();
    expect(within(region).queryByRole("link")).not.toBeInTheDocument();
    expect(within(region).queryByText(/pickup/i)).not.toBeInTheDocument();
  });

  it("links to Bring Your Idea for custom work", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(new Error("offline"));
    renderChannels();
    expect(screen.getByRole("link", { name: /bring your idea/i })).toHaveAttribute("href", "/bring-your-idea");
  });
});
