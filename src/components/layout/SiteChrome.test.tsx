import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { SiteChrome } from "./SiteChrome";
import { isAdminPath } from "./useAdminChrome";
import { useAuth, type AuthContextValue } from "@/lib/auth/AuthProvider";

// Redesign Batch 9 (decision D5): an administrator on /admin/* gets no
// storefront header, footer or <main> (AdminShell supplies its own chrome and
// main); everyone else — and every non-admin route — keeps the storefront
// chrome, so an /admin URL looks like any other page to a customer or guest.

vi.mock("@/lib/auth/AuthProvider", () => ({ useAuth: vi.fn() }));
const mockedUseAuth = vi.mocked(useAuth);
let mockPathname = "/admin/orders";
vi.mock("next/navigation", () => ({ usePathname: () => mockPathname }));

function auth(role: "admin" | "customer" | null, isLoading = false): AuthContextValue {
  return {
    user: role
      ? {
          id: "u",
          email: "u@example.com",
          role,
          emailVerified: true,
          emailVerifiedAt: null,
          createdAt: "2026-01-01T00:00:00Z",
        }
      : null,
    isAuthenticated: role !== null,
    isLoading,
    isError: false,
    logout: vi.fn(),
  };
}

function renderChrome() {
  return render(
    <SiteChrome header={<span>Store header</span>} footer={<span>Store footer</span>}>
      <p>Page</p>
    </SiteChrome>
  );
}

beforeEach(() => {
  mockPathname = "/admin/orders";
});

describe("SiteChrome", () => {
  it("drops the storefront header, footer and main for an administrator on /admin", () => {
    mockedUseAuth.mockReturnValue(auth("admin"));
    renderChrome();
    expect(screen.getByText("Page")).toBeInTheDocument();
    expect(screen.queryByText("Store header")).not.toBeInTheDocument();
    expect(screen.queryByText("Store footer")).not.toBeInTheDocument();
    expect(screen.queryByRole("main")).not.toBeInTheDocument();
  });

  it.each([
    ["a customer", auth("customer")],
    ["a guest", auth(null)],
    ["a still-loading session", auth(null, true)],
  ])("keeps the storefront chrome on /admin for %s", (_label, state) => {
    mockedUseAuth.mockReturnValue(state);
    renderChrome();
    expect(screen.getByRole("banner")).toHaveTextContent("Store header");
    expect(screen.getByRole("main")).toHaveTextContent("Page");
    expect(screen.getByRole("contentinfo")).toHaveTextContent("Store footer");
  });

  it("keeps the storefront chrome for an administrator outside /admin", () => {
    mockPathname = "/shop";
    mockedUseAuth.mockReturnValue(auth("admin"));
    renderChrome();
    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
  });

  it("matches only real /admin paths", () => {
    expect(isAdminPath("/admin")).toBe(true);
    expect(isAdminPath("/admin/orders/1")).toBe(true);
    expect(isAdminPath("/administrator")).toBe(false);
    expect(isAdminPath("/account")).toBe(false);
    expect(isAdminPath(null)).toBe(false);
  });
});
