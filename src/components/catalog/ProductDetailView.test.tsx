import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/apiClient";
import { useAuth, type AuthContextValue } from "@/lib/auth/AuthProvider";
import { ProductDetailView } from "./ProductDetailView";

vi.mock("@/lib/auth/AuthProvider", () => ({ useAuth: vi.fn() }));
const mockedUseAuth = vi.mocked(useAuth);

function authState(overrides: Partial<AuthContextValue> = {}): AuthContextValue {
  return { user: null, isAuthenticated: false, isLoading: false, isError: false, logout: vi.fn(), ...overrides };
}

function renderDetail(slug = "dragon") {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <ProductDetailView slug={slug} />
    </QueryClientProvider>
  );
}

const physicalDetail = {
  id: "p1",
  type: "physical",
  name: "Articulated Dragon",
  slug: "dragon",
  cover_image: { id: "img1", url: "/media/products/dragon.png", alt_text: "Dragon", is_cover: true },
  price: { amount_cents: 1800, currency: "USD" },
  category: { id: "c1", name: "Toys and Figures", slug: "toys-figures" },
  material: { id: "m1", name: "PLA" },
  colour: { id: "co1", name: "Red" },
  is_available: true,
  purchase_mode: "both",
  average_rating: 0,
  review_count: 0,
  is_featured: false,
  description: "A fully articulated dragon.",
  images: [{ id: "img1", url: "/media/products/dragon.png", alt_text: "Dragon", is_cover: true }],
  seo_title: null,
  seo_description: null,
  og_image_url: null,
  dimensions: { length_mm: 120, width_mm: 80, height_mm: 60 },
  production_lead_time_days: 2,
  batch_size: 2,
  max_quantity_per_line: 5,
  capabilities: { can_add_to_cart: true, can_offer: false, whatsapp_available: true },
};

const stlDetail = {
  ...physicalDetail,
  type: "stl",
  slug: "dragon-stl",
  material: null,
  colour: null,
  purchase_mode: null,
  dimensions: null,
  production_lead_time_days: null,
  batch_size: null,
  max_quantity_per_line: null,
  capabilities: { can_add_to_cart: true, can_offer: true, whatsapp_available: false },
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ProductDetailView", () => {
  it("shows a loading spinner while the product is loading", () => {
    vi.spyOn(apiClient, "get").mockImplementation(() => new Promise(() => {}));
    mockedUseAuth.mockReturnValue(authState());

    renderDetail();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders the app's real not-found content on a 404", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue({ kind: "http", status: 404, message: "x", raw: {} });
    mockedUseAuth.mockReturnValue(authState());

    renderDetail("unknown-slug");

    expect(await screen.findByRole("heading", { name: /page not found/i })).toBeInTheDocument();
  });

  it("shows a generic error alert on a non-404 failure", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue({ kind: "http", status: 500, message: "x", raw: {} });
    mockedUseAuth.mockReturnValue(authState());

    renderDetail();

    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn.t load this product/i);
  });

  it("renders a physical product's price, material, colour, and dimensions", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (path: unknown) => {
      if ((path as string).startsWith("/api/v1/settings/public")) {
        return { accepting_orders: true, cash_payment_enabled: true, cash_max_order_total: { amount_cents: 10000, currency: "USD" }, pickup_address: null, pickup_hours: null, whatsapp_number: "+96170000000" };
      }
      return physicalDetail;
    });
    mockedUseAuth.mockReturnValue(authState());

    renderDetail("dragon");

    expect(await screen.findByRole("heading", { name: "Articulated Dragon" })).toBeInTheDocument();
    expect(screen.getByText("$18.00")).toBeInTheDocument();
    expect(screen.getByText("PLA")).toBeInTheDocument();
    expect(screen.getByText("Red")).toBeInTheDocument();
    expect(screen.getByText(/120.*80.*60 mm/)).toBeInTheDocument();
    expect(screen.queryByText(/currently unavailable/i)).not.toBeInTheDocument();
  });

  it("renders an STL product's null physical-only fields as absent — no empty labels", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (path: unknown) => {
      if ((path as string).startsWith("/api/v1/settings/public")) {
        return { accepting_orders: true, cash_payment_enabled: true, cash_max_order_total: { amount_cents: 10000, currency: "USD" }, pickup_address: null, pickup_hours: null, whatsapp_number: null };
      }
      return stlDetail;
    });
    mockedUseAuth.mockReturnValue(authState());

    renderDetail("dragon-stl");

    expect(await screen.findByRole("heading", { name: "Articulated Dragon" })).toBeInTheDocument();
    expect(screen.queryByText(/material:/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/colour:/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/dimensions:/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/production lead time/i)).not.toBeInTheDocument();
  });

  it("shows UnavailableNotice when the product is unavailable", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (path: unknown) => {
      if ((path as string).startsWith("/api/v1/settings/public")) {
        return { accepting_orders: true, cash_payment_enabled: true, cash_max_order_total: { amount_cents: 10000, currency: "USD" }, pickup_address: null, pickup_hours: null, whatsapp_number: null };
      }
      return { ...physicalDetail, is_available: false, capabilities: { can_add_to_cart: false, can_offer: false, whatsapp_available: false } };
    });
    mockedUseAuth.mockReturnValue(authState());

    renderDetail();

    expect(await screen.findByText(/currently unavailable/i)).toBeInTheDocument();
  });

  it("shows the WhatsApp CTA when whatsapp_available is true and a number is configured", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (path: unknown) => {
      if ((path as string).startsWith("/api/v1/settings/public")) {
        return { accepting_orders: true, cash_payment_enabled: true, cash_max_order_total: { amount_cents: 10000, currency: "USD" }, pickup_address: null, pickup_hours: null, whatsapp_number: "+96170000000" };
      }
      return physicalDetail;
    });
    mockedUseAuth.mockReturnValue(authState());

    renderDetail();

    expect(await screen.findByRole("link", { name: /chat on whatsapp/i })).toBeInTheDocument();
  });

  it("never shows the WhatsApp CTA when whatsapp_available is false", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (path: unknown) => {
      if ((path as string).startsWith("/api/v1/settings/public")) {
        return { accepting_orders: true, cash_payment_enabled: true, cash_max_order_total: { amount_cents: 10000, currency: "USD" }, pickup_address: null, pickup_hours: null, whatsapp_number: "+96170000000" };
      }
      return stlDetail;
    });
    mockedUseAuth.mockReturnValue(authState());

    renderDetail("dragon-stl");

    await screen.findByRole("heading", { name: "Articulated Dragon" });
    expect(screen.queryByRole("link", { name: /chat on whatsapp/i })).not.toBeInTheDocument();
  });
  describe("Add to cart (Phase 5C)", () => {
    const VERIFIED = {
      id: "u-1",
      email: "a@b.c",
      role: "customer",
      emailVerified: true,
      emailVerifiedAt: "2026-01-01T00:00:00Z",
      createdAt: "2026-01-01T00:00:00Z",
    };
    const settings = { accepting_orders: true, cash_payment_enabled: true, cash_max_order_total: { amount_cents: 10000, currency: "USD" }, pickup_address: null, pickup_hours: null, whatsapp_number: "+96170000000" };

    function serve(detail: object) {
      vi.spyOn(apiClient, "get").mockImplementation(async (path: unknown) =>
        (path as string).startsWith("/api/v1/settings/public") ? settings : detail
      );
    }

    it("a verified customer gets a real Add to cart button with a quantity control for a physical product", async () => {
      serve(physicalDetail);
      mockedUseAuth.mockReturnValue(authState({ user: VERIFIED, isAuthenticated: true }));
      renderDetail();
      expect(await screen.findByRole("button", { name: "Add to cart" })).toBeInTheDocument();
      expect(screen.getByRole("group", { name: "Quantity of Articulated Dragon" })).toBeInTheDocument();
      expect(screen.getByText("Maximum 5 per order")).toBeInTheDocument();
    });

    it("an STL product gets Add to cart with no quantity control", async () => {
      serve(stlDetail);
      mockedUseAuth.mockReturnValue(authState({ user: VERIFIED, isAuthenticated: true }));
      renderDetail("dragon-stl");
      expect(await screen.findByRole("button", { name: "Add to cart" })).toBeInTheDocument();
      expect(screen.queryByRole("group", { name: /quantity/i })).not.toBeInTheDocument();
    });

    it("a WhatsApp-only product (can_add_to_cart false) offers WhatsApp and no cart action at all", async () => {
      serve({
        ...physicalDetail,
        purchase_mode: "whatsapp_only",
        capabilities: { can_add_to_cart: false, can_offer: false, whatsapp_available: true },
      });
      mockedUseAuth.mockReturnValue(authState({ user: VERIFIED, isAuthenticated: true }));
      renderDetail();
      expect(await screen.findByRole("link", { name: /chat on whatsapp/i })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /add to cart/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("link", { name: /add to cart/i })).not.toBeInTheDocument();
    });

    it("an unavailable product (can_add_to_cart false) has no cart action", async () => {
      serve({ ...physicalDetail, is_available: false, capabilities: { can_add_to_cart: false, can_offer: false, whatsapp_available: false } });
      mockedUseAuth.mockReturnValue(authState({ user: VERIFIED, isAuthenticated: true }));
      renderDetail();
      expect(await screen.findByText(/currently unavailable/i)).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /add to cart/i })).not.toBeInTheDocument();
    });
  });
});
