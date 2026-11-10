import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { AccountLayout } from "./AccountLayout";
import { useAuth, type AuthContextValue } from "@/lib/auth/AuthProvider";
import type { SafeUser } from "@/lib/auth/authSession";

// FVS-006-IMPLEMENTATION-PLAN.md T02 — AccountLayout composes the existing
// ProtectedRoute (never a second, duplicated boundary) and renders the
// nav/content shell only once ProtectedRoute actually lets children
// through. Mocks useAuth directly, same precedent as
// ProtectedRoute.test.tsx — ProtectedRoute's own redirect/loading/error
// behavior is proven there, not re-proven here.

vi.mock("@/lib/auth/AuthProvider", () => ({ useAuth: vi.fn() }));
const mockedUseAuth = vi.mocked(useAuth);

let mockPathname = "/account/profile";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => mockPathname,
  useSearchParams: () => new URLSearchParams(),
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

const STUB_USER: SafeUser = {
  id: "u-1",
  email: "ada@example.com",
  role: "customer",
  emailVerified: true,
  emailVerifiedAt: null,
  createdAt: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  mockedUseAuth.mockReset();
  mockPathname = "/account/profile";
});

describe("AccountLayout", () => {
  it("renders an accessible nav and the content region once authenticated", () => {
    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true, user: STUB_USER }));
    render(
      <AccountLayout>
        <div data-testid="page-content">profile content</div>
      </AccountLayout>
    );

    expect(screen.getByRole("navigation", { name: "Account" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Account content" })).toBeInTheDocument();
    expect(screen.getByTestId("page-content")).toBeInTheDocument();
  });

  it("renders exactly the registered nav items — Profile and Notifications, today", () => {
    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true, user: STUB_USER }));
    render(
      <AccountLayout>
        <div>content</div>
      </AccountLayout>
    );

    const nav = screen.getByRole("navigation", { name: "Account" });
    const links = nav.querySelectorAll("a");
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveTextContent("Profile");
    expect(links[0]).toHaveAttribute("href", "/account/profile");
    expect(links[1]).toHaveTextContent("Notifications");
    expect(links[1]).toHaveAttribute("href", "/account/notifications");
  });

  it("mounts the shared Log out control for a signed-in user (Phase 5A defect 7)", () => {
    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true, user: STUB_USER }));
    render(
      <AccountLayout>
        <div>content</div>
      </AccountLayout>
    );

    expect(screen.getAllByRole("button", { name: "Log out" })).toHaveLength(1);
  });

  it("marks the active route with aria-current='page'", () => {
    mockPathname = "/account/profile";
    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true, user: STUB_USER }));
    render(
      <AccountLayout>
        <div>content</div>
      </AccountLayout>
    );

    expect(screen.getByRole("link", { name: "Profile" })).toHaveAttribute("aria-current", "page");
  });

  it("does not mark an inactive route as the active one", () => {
    mockPathname = "/account/orders";
    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true, user: STUB_USER }));
    render(
      <AccountLayout>
        <div>content</div>
      </AccountLayout>
    );

    expect(screen.getByRole("link", { name: "Profile" })).not.toHaveAttribute("aria-current");
  });

  it("never creates a second <main> landmark", () => {
    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true, user: STUB_USER }));
    render(
      <AccountLayout>
        <div>content</div>
      </AccountLayout>
    );

    expect(document.querySelectorAll("main")).toHaveLength(0);
  });

  it("renders only the loading state (no nav/content) while auth is loading — delegated to ProtectedRoute", () => {
    mockedUseAuth.mockReturnValue(authState({ isLoading: true }));
    render(
      <AccountLayout>
        <div data-testid="page-content">content</div>
      </AccountLayout>
    );

    expect(screen.queryByRole("navigation", { name: "Account" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("page-content")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders nothing while anonymous — delegated to ProtectedRoute's redirect", () => {
    mockedUseAuth.mockReturnValue(authState({}));
    render(
      <AccountLayout>
        <div data-testid="page-content">content</div>
      </AccountLayout>
    );

    expect(screen.queryByRole("navigation", { name: "Account" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("page-content")).not.toBeInTheDocument();
  });

  it("renders the shell anyway when the auth query errors, so the page can show its own retry UI", () => {
    mockedUseAuth.mockReturnValue(authState({ isError: true }));
    render(
      <AccountLayout>
        <div data-testid="page-content">content</div>
      </AccountLayout>
    );

    expect(screen.getByRole("navigation", { name: "Account" })).toBeInTheDocument();
    expect(screen.getByTestId("page-content")).toBeInTheDocument();
  });
});
