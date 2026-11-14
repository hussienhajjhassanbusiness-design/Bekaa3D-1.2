import { describe, it, expect, vi, beforeEach } from "vitest";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AdminShell } from "./AdminShell";
import { useAuth, type AuthContextValue } from "@/lib/auth/AuthProvider";
import type { SafeUser } from "@/lib/auth/authSession";

// Mirrors AccountLayout.test.tsx's own precedent: AdminGuard's
// loading/anonymous/isError/not-admin behavior is proven in
// AdminGuard.test.tsx, not re-proven here — this file only proves the
// nav/content shell AdminShell adds once AdminGuard lets children
// through, plus the admin-specific "customer never sees an admin nav
// item, even a disabled one" rule.
vi.mock("@/lib/auth/AuthProvider", () => ({ useAuth: vi.fn() }));
const mockedUseAuth = vi.mocked(useAuth);

let mockPathname = "/admin/settings";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => mockPathname,
}));

function authState(overrides: Partial<AuthContextValue>): AuthContextValue {
  return {
    user: null,
    isAuthenticated: false,
    isLoading: false,
    isError: false,
    logout: vi.fn(),
    ...overrides,
  };
}

const ADMIN_USER: SafeUser = {
  id: "u-1",
  email: "admin@example.com",
  role: "admin",
  emailVerified: true,
  emailVerifiedAt: null,
  createdAt: "2026-01-01T00:00:00Z",
};

const CUSTOMER_USER: SafeUser = { ...ADMIN_USER, role: "customer" };

beforeEach(() => {
  mockedUseAuth.mockReset();
  mockPathname = "/admin/settings";
});

describe("AdminShell", () => {
  it("renders an accessible nav and the content region for a signed-in administrator", () => {
    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true, user: ADMIN_USER }));
    render(
      <AdminShell>
        <div data-testid="page-content">settings</div>
      </AdminShell>
    );

    expect(screen.getByRole("navigation", { name: "Admin" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Admin content" })).toBeInTheDocument();
    expect(screen.getByTestId("page-content")).toBeInTheDocument();
  });

  it("renders exactly the built admin nav items, with no entry for an unbuilt area", () => {
    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true, user: ADMIN_USER }));
    render(
      <AdminShell>
        <div>content</div>
      </AdminShell>
    );

    const nav = screen.getByRole("navigation", { name: "Admin" });
    const links = Array.from(nav.querySelectorAll("a")).map((a) => a.textContent);
    expect(links).toEqual([
      "Orders",
      "STL deliveries",
      "Offers",
      "Payments",
      "Refunds",
      "Cash blocks",
      "Contact messages",
      "Bring Your Idea",
      "Settings",
      "Customers",
      "Categories",
      "Materials",
      "Colours",
      "Products",
    ]);
    expect(nav.textContent).not.toMatch(/cancellation|shipping|entitlement/i);
  });

  it("mounts the shared Log out control for a signed-in administrator (Phase 5A defect 7)", () => {
    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true, user: ADMIN_USER }));
    render(
      <AdminShell>
        <div>content</div>
      </AdminShell>
    );

    expect(screen.getAllByRole("button", { name: "Log out" })).toHaveLength(1);
  });

  it("marks the active route with aria-current='page'", () => {
    mockPathname = "/admin/products";
    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true, user: ADMIN_USER }));
    render(
      <AdminShell>
        <div>content</div>
      </AdminShell>
    );

    expect(screen.getByRole("link", { name: "Products" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Settings" })).not.toHaveAttribute("aria-current");
  });

  it("marks a nested route (e.g. a product detail page) as active on its parent nav item", () => {
    mockPathname = "/admin/products/abc-123/edit";
    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true, user: ADMIN_USER }));
    render(
      <AdminShell>
        <div>content</div>
      </AdminShell>
    );

    expect(screen.getByRole("link", { name: "Products" })).toHaveAttribute("aria-current", "page");
  });

  it("renders the real not-found page, with no admin nav, for a signed-in customer", () => {
    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true, user: CUSTOMER_USER }));
    render(
      <AdminShell>
        <div data-testid="page-content">settings</div>
      </AdminShell>
    );

    expect(screen.queryByRole("navigation", { name: "Admin" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("page-content")).not.toBeInTheDocument();
    expect(screen.getByText(/404/)).toBeInTheDocument();
  });

  // Batch 9 (D5): the admin shell owns the chrome for an administrator —
  // SiteChrome renders no storefront <main> then — so the shell supplies the
  // page's single main landmark (the skip-link target), with the sidebar
  // outside it.
  it("renders exactly one <main id='main-content'> landmark, with the admin nav outside it", () => {
    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true, user: ADMIN_USER }));
    render(
      <AdminShell>
        <div>content</div>
      </AdminShell>
    );

    expect(document.querySelectorAll("main")).toHaveLength(1);
    const main = screen.getByRole("main");
    expect(main).toHaveAttribute("id", "main-content");
    expect(main).toHaveAttribute("tabindex", "-1");
    expect(main).not.toContainElement(screen.getByRole("navigation", { name: "Admin" }));
  });
});

describe("AdminShell (redesign Batch 9 drawer and top bar)", () => {
  // jsdom has no matchMedia; the open drawer listens for the desktop breakpoint.
  type ChangeListener = (event: { matches: boolean }) => void;
  let mediaListeners: ChangeListener[] = [];
  beforeEach(() => {
    mediaListeners = [];
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      addEventListener: (_type: string, listener: ChangeListener) => mediaListeners.push(listener),
      removeEventListener: (_type: string, listener: ChangeListener) => {
        mediaListeners = mediaListeners.filter((l) => l !== listener);
      },
    })) as unknown as typeof window.matchMedia;
  });

  it("closes the drawer when the viewport grows to the desktop sidebar width", async () => {
    const user = userEvent.setup();
    renderAdmin();
    await user.click(screen.getByRole("button", { name: "Open admin menu" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    act(() => mediaListeners.forEach((listener) => listener({ matches: true })));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  function renderAdmin() {
    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true, user: ADMIN_USER }));
    return render(
      <AdminShell>
        <div>content</div>
      </AdminShell>
    );
  }

  it("names the current area and the signed-in administrator in the top bar", () => {
    mockPathname = "/admin/orders/abc";
    renderAdmin();
    const banner = screen.getByRole("banner");
    expect(banner).toHaveTextContent("Orders");
    expect(banner).toHaveTextContent("admin@example.com");
  });

  it("groups the nav under section labels without changing the link order", () => {
    renderAdmin();
    const nav = screen.getByRole("navigation", { name: "Admin" });
    for (const label of ["Fulfilment", "Money", "Enquiries", "Store", "Catalogue"]) {
      expect(nav).toHaveTextContent(label);
    }
  });

  it("opens the nav drawer as a labelled modal dialog, moves focus in, and closes on Escape with focus returned", async () => {
    const user = userEvent.setup();
    renderAdmin();
    const trigger = screen.getByRole("button", { name: "Open admin menu" });
    await user.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Admin menu" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByRole("button", { name: "Close admin menu" })).toHaveFocus();
    expect(within(dialog).getByRole("navigation", { name: "Admin" })).toBeInTheDocument();
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("closes the drawer when the route changes", async () => {
    const user = userEvent.setup();
    const { rerender } = renderAdmin();
    await user.click(screen.getByRole("button", { name: "Open admin menu" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    mockPathname = "/admin/payments";
    rerender(
      <AdminShell>
        <div>content</div>
      </AdminShell>
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("marks the active item inside the drawer too", async () => {
    const user = userEvent.setup();
    mockPathname = "/admin/refunds";
    renderAdmin();
    await user.click(screen.getByRole("button", { name: "Open admin menu" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("link", { name: "Refunds" })).toHaveAttribute("aria-current", "page");
  });
});
