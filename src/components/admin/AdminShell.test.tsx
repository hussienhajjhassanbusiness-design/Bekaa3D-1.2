import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
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
    expect(links).toEqual(["Orders", "STL deliveries", "Payments", "Refunds", "Settings", "Customers", "Categories", "Materials", "Colours", "Products"]);
    expect(nav.textContent).not.toMatch(/cancellation|contact|shipping|entitlement/i);
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

  it("never creates a second <main> landmark", () => {
    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true, user: ADMIN_USER }));
    render(
      <AdminShell>
        <div>content</div>
      </AdminShell>
    );

    expect(document.querySelectorAll("main")).toHaveLength(0);
  });
});
