import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
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

  it("shows the server's promotional price, the original, the campaign and its real end date", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (path: unknown) => {
      if ((path as string).startsWith("/api/v1/settings/public")) {
        return { accepting_orders: true, cash_payment_enabled: true, cash_max_order_total: { amount_cents: 10000, currency: "USD" }, pickup_address: null, pickup_hours: null, whatsapp_number: null };
      }
      return {
        ...physicalDetail,
        price: { amount_cents: 1440, currency: "USD" },
        list_price: { amount_cents: 1800, currency: "USD" },
        promotion: { id: "promo-1", name: "Ramadan Sale", badge_text: null, discount_type: "percentage", discount_value: 20, ends_at: "2026-12-20T12:00:00Z" },
      };
    });
    mockedUseAuth.mockReturnValue(authState());

    renderDetail("dragon");

    expect(await screen.findByRole("heading", { name: "Articulated Dragon" })).toBeInTheDocument();
    expect(screen.getByText("$14.40")).toBeInTheDocument();
    expect(screen.getByText("$18.00").closest("s")).not.toBeNull();
    expect(screen.getByText(/Current promotional price:/)).toBeInTheDocument();
    expect(screen.getByText(/Original price:/)).toBeInTheDocument();
    expect(screen.getByText("20% OFF")).toBeInTheDocument();
    expect(screen.getByText(/Ramadan Sale/)).toBeInTheDocument();
    expect(document.querySelector('time[datetime="2026-12-20T12:00:00Z"]')).not.toBeNull();
  });

  it("shows no promotion UI when the server reports none", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (path: unknown) => {
      if ((path as string).startsWith("/api/v1/settings/public")) {
        return { accepting_orders: true, cash_payment_enabled: true, cash_max_order_total: { amount_cents: 10000, currency: "USD" }, pickup_address: null, pickup_hours: null, whatsapp_number: null };
      }
      return { ...physicalDetail, list_price: physicalDetail.price, promotion: null };
    });
    mockedUseAuth.mockReturnValue(authState());

    renderDetail("dragon");

    expect(await screen.findByRole("heading", { name: "Articulated Dragon" })).toBeInTheDocument();
    expect(screen.queryByText(/Original price:/)).toBeNull();
    expect(screen.queryByText(/% OFF/)).toBeNull();
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
    // Batch 3: the labels are spec-tile terms (no trailing colon); none of
    // them, nor the Specifications section itself, may render for an STL.
    expect(screen.queryByText("Material", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText("Colour", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText("Dimensions", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText(/production lead time/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Specifications" })).not.toBeInTheDocument();
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

  // Stabilization: a WhatsApp-only product with no configured number was a dead end.
  it("points a WhatsApp-only product to Contact when no WhatsApp number is configured", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (path: unknown) => {
      if ((path as string).startsWith("/api/v1/settings/public")) {
        return { accepting_orders: true, cash_payment_enabled: true, cash_max_order_total: { amount_cents: 10000, currency: "USD" }, pickup_address: null, pickup_hours: null, whatsapp_number: null };
      }
      return { ...physicalDetail, purchase_mode: "whatsapp_only", capabilities: { can_add_to_cart: false, can_offer: false, whatsapp_available: true } };
    });
    mockedUseAuth.mockReturnValue(authState());

    renderDetail();

    expect(await screen.findByText(/ordered over whatsapp, which isn.t available right now/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /contact us to order it/i })).toHaveAttribute("href", "/contact");
    expect(screen.queryByRole("link", { name: /chat on whatsapp/i })).not.toBeInTheDocument();
  });

  it("does not show the Contact fallback when WhatsApp is configured or the item can go in the cart", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (path: unknown) => {
      if ((path as string).startsWith("/api/v1/settings/public")) {
        return { accepting_orders: true, cash_payment_enabled: true, cash_max_order_total: { amount_cents: 10000, currency: "USD" }, pickup_address: null, pickup_hours: null, whatsapp_number: null };
      }
      return physicalDetail; // can_add_to_cart: true
    });
    mockedUseAuth.mockReturnValue(authState());

    renderDetail();

    await screen.findByRole("heading", { name: "Articulated Dragon" });
    expect(screen.queryByText(/ordered over whatsapp/i)).not.toBeInTheDocument();
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

  describe("Batch 3 layout", () => {
    function mockDetail(detail: Record<string, unknown>, whatsappNumber: string | null = "+96170000000") {
      vi.spyOn(apiClient, "get").mockImplementation(async (path: unknown) => {
        const p = path as string;
        if (p.startsWith("/api/v1/settings/public")) {
          return { accepting_orders: true, cash_payment_enabled: true, cash_max_order_total: { amount_cents: 10000, currency: "USD" }, pickup_address: null, pickup_hours: null, whatsapp_number: whatsappNumber };
        }
        return detail;
      });
    }

    it("renders a breadcrumb: Shop, the real category filter link, then the current product", async () => {
      mockDetail(physicalDetail);
      mockedUseAuth.mockReturnValue(authState());
      renderDetail("dragon");

      const crumb = await screen.findByRole("navigation", { name: "Breadcrumb" });
      expect(within(crumb).getByRole("link", { name: "Shop" })).toHaveAttribute("href", "/shop");
      expect(within(crumb).getByRole("link", { name: "Toys and Figures" })).toHaveAttribute("href", "/shop?category=c1");
      expect(within(crumb).getByText("Articulated Dragon")).toHaveAttribute("aria-current", "page");
    });

    it("keeps a clean heading outline: one h1, then h2 sections", async () => {
      mockDetail(physicalDetail);
      mockedUseAuth.mockReturnValue(authState());
      renderDetail("dragon");

      await screen.findByRole("heading", { level: 1, name: "Articulated Dragon" });
      expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
      expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual(["Specifications", "Description"]);
    });

    it("presents real physical specs as term/definition pairs", async () => {
      mockDetail(physicalDetail);
      mockedUseAuth.mockReturnValue(authState());
      renderDetail("dragon");

      await screen.findByRole("heading", { level: 1 });
      expect(screen.getAllByRole("term").map((t) => t.textContent)).toEqual(["Material", "Colour", "Dimensions", "Production lead time"]);
      expect(screen.getAllByRole("definition").map((d) => d.textContent)).toEqual(["PLA", "Red", "120 × 80 × 60 mm", "2 days"]);
    });

    it("shows the real rating only when the product has reviews", async () => {
      mockDetail({ ...physicalDetail, average_rating: 4.5, review_count: 12 });
      mockedUseAuth.mockReturnValue(authState());
      renderDetail("dragon");

      expect(await screen.findByText("Rated 4.5 out of 5 from 12 reviews")).toBeInTheDocument();
    });

    it("never shows a rating, stock, SKU or datasheet that the contract does not supply", async () => {
      mockDetail(physicalDetail);
      mockedUseAuth.mockReturnValue(authState());
      renderDetail("dragon");

      await screen.findByRole("heading", { level: 1 });
      expect(screen.queryByText(/rated|review/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/in stock|sku|datasheet/i)).not.toBeInTheDocument();
    });

    it("shows the no-image placeholder (never a broken image) when the product has no images", async () => {
      mockDetail({ ...physicalDetail, images: [], cover_image: null });
      mockedUseAuth.mockReturnValue(authState());
      renderDetail("dragon");

      expect(await screen.findByText(/no image available/i)).toBeInTheDocument();
      expect(screen.queryByTestId("product-gallery-main-image")).not.toBeInTheDocument();
    });

    it("anonymous, offer-capable STL: Add to cart, Make an offer and wishlist are sign-in links with the product returnTo", async () => {
      mockDetail(stlDetail, null);
      mockedUseAuth.mockReturnValue(authState());
      renderDetail("dragon-stl");

      const returnTo = "/login?returnTo=%2Fshop%2Fdragon-stl";
      expect(await screen.findByRole("link", { name: "Add to cart" })).toHaveAttribute("href", returnTo);
      expect(screen.getByRole("link", { name: "Make an offer" })).toHaveAttribute("href", returnTo);
      expect(screen.getByRole("link", { name: "Save to wishlist" })).toHaveAttribute("href", returnTo);
    });

    it("no Make an offer without the server's can_offer capability", async () => {
      mockDetail({ ...stlDetail, capabilities: { can_add_to_cart: true, can_offer: false, whatsapp_available: false } }, null);
      mockedUseAuth.mockReturnValue(authState());
      renderDetail("dragon-stl");

      await screen.findByRole("link", { name: "Add to cart" });
      expect(screen.queryByRole("link", { name: "Make an offer" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Make an offer" })).not.toBeInTheDocument();
    });

    it("keeps the description's own line breaks", async () => {
      mockDetail({ ...physicalDetail, description: "Line one.\n\nLine two." });
      mockedUseAuth.mockReturnValue(authState());
      renderDetail("dragon");

      expect(await screen.findByText(/Line one\./)).toHaveClass("whitespace-pre-line");
    });
  });
});
