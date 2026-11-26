import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { ProtectedRoute } from "./ProtectedRoute";
import { useAuth, type AuthContextValue } from "@/lib/auth/AuthProvider";
import type { SafeUser } from "@/lib/auth/authSession";

// FVS-003-IMPLEMENTATION-PLAN.md §9/Part D (confirmed BATCH 3B) — gates
// rendering on the REAL AuthProvider interface ({user, isAuthenticated,
// isLoading}). Mocks useAuth directly (AuthProvider's own wiring to the
// ["auth","session"] query is proven in authSession/AuthProvider's own
// tests) and next/navigation, matching the login-page-test precedent.

vi.mock("@/lib/auth/AuthProvider", () => ({ useAuth: vi.fn() }));
const mockedUseAuth = vi.mocked(useAuth);

const mockReplace = vi.fn();
const mockRouter = { replace: mockReplace };
let mockPathname = "/account";
let mockSearchParams = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => mockRouter,
  usePathname: () => mockPathname,
  useSearchParams: () => mockSearchParams,
}));

beforeEach(() => {
  mockedUseAuth.mockReset();
  mockReplace.mockReset();
  mockPathname = "/account";
  mockSearchParams = new URLSearchParams();
});

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

describe("ProtectedRoute", () => {
  it("renders only the LoadingSpinner while auth is loading — never the children", () => {
    mockedUseAuth.mockReturnValue(authState({ isLoading: true }));
    render(
      <ProtectedRoute>
        <div data-testid="protected-content">secret</div>
      </ProtectedRoute>
    );

    expect(screen.queryByTestId("protected-content")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("renders the children once authenticated", () => {
    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true, user: STUB_USER }));
    render(
      <ProtectedRoute>
        <div data-testid="protected-content">secret</div>
      </ProtectedRoute>
    );

    expect(screen.getByTestId("protected-content")).toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("never renders the children while anonymous", () => {
    mockedUseAuth.mockReturnValue(authState({}));
    render(
      <ProtectedRoute>
        <div data-testid="protected-content">secret</div>
      </ProtectedRoute>
    );

    expect(screen.queryByTestId("protected-content")).not.toBeInTheDocument();
  });

  it("redirects to /login with the current path encoded as returnTo when anonymous", async () => {
    mockPathname = "/account";
    mockedUseAuth.mockReturnValue(authState({}));
    render(
      <ProtectedRoute>
        <div>secret</div>
      </ProtectedRoute>
    );

    await waitFor(() => expect(mockReplace).toHaveBeenCalledTimes(1));
    expect(mockReplace).toHaveBeenCalledWith("/login?returnTo=%2Faccount");
  });

  it("preserves the query string in the returnTo redirect, with no origin embedded", async () => {
    mockPathname = "/orders";
    mockSearchParams = new URLSearchParams("tab=open");
    mockedUseAuth.mockReturnValue(authState({}));
    render(
      <ProtectedRoute>
        <div>secret</div>
      </ProtectedRoute>
    );

    await waitFor(() => expect(mockReplace).toHaveBeenCalledTimes(1));
    const [redirectPath] = mockReplace.mock.calls[0] as [string];
    expect(redirectPath).toBe("/login?returnTo=%2Forders%3Ftab%3Dopen");
    expect(redirectPath).not.toMatch(/https?:\/\//);
  });

  it("does not redirect while still loading", () => {
    mockedUseAuth.mockReturnValue(authState({ isLoading: true }));
    render(
      <ProtectedRoute>
        <div>secret</div>
      </ProtectedRoute>
    );

    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("does not redirect once authenticated", () => {
    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true }));
    render(
      <ProtectedRoute>
        <div>secret</div>
      </ProtectedRoute>
    );

    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("transitioning from loading to authenticated renders children without ever having rendered them early", () => {
    mockedUseAuth.mockReturnValue(authState({ isLoading: true }));
    const { rerender } = render(
      <ProtectedRoute>
        <div data-testid="protected-content">secret</div>
      </ProtectedRoute>
    );
    expect(screen.queryByTestId("protected-content")).not.toBeInTheDocument();

    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true }));
    rerender(
      <ProtectedRoute>
        <div data-testid="protected-content">secret</div>
      </ProtectedRoute>
    );
    expect(screen.getByTestId("protected-content")).toBeInTheDocument();
  });

  it("transitioning from loading to anonymous never renders children and redirects exactly once", async () => {
    mockedUseAuth.mockReturnValue(authState({ isLoading: true }));
    const { rerender } = render(
      <ProtectedRoute>
        <div data-testid="protected-content">secret</div>
      </ProtectedRoute>
    );

    mockedUseAuth.mockReturnValue(authState({}));
    rerender(
      <ProtectedRoute>
        <div data-testid="protected-content">secret</div>
      </ProtectedRoute>
    );

    expect(screen.queryByTestId("protected-content")).not.toBeInTheDocument();
    await waitFor(() => expect(mockReplace).toHaveBeenCalledTimes(1));
  });

  // FVS-006-IMPLEMENTATION-PLAN.md T01 — an unexpected transport/server
  // failure (AuthProvider's isError:true) says nothing about whether the
  // session is actually valid. Redirecting to /login in this case would
  // reproduce the exact cross-slice defect found and fixed at FVS-006:
  // bouncing a possibly-still-authenticated customer out on a transient
  // blip. ProtectedRoute must render children (not redirect) so the page
  // itself can show its own retryable error via useAuth().isError.
  it("renders children (not a redirect) when the auth query genuinely errors, even though isAuthenticated is false", () => {
    mockedUseAuth.mockReturnValue(authState({ isError: true }));
    render(
      <ProtectedRoute>
        <div data-testid="protected-content">secret</div>
      </ProtectedRoute>
    );

    expect(screen.getByTestId("protected-content")).toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("does not redirect when the auth query genuinely errors", async () => {
    mockedUseAuth.mockReturnValue(authState({ isError: true }));
    render(
      <ProtectedRoute>
        <div>secret</div>
      </ProtectedRoute>
    );

    // Give any stray effect a tick to fire, then confirm it never did.
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("does not call replace more than once across re-renders while anonymous", async () => {
    mockedUseAuth.mockReturnValue(authState({}));
    const { rerender } = render(
      <ProtectedRoute>
        <div>secret</div>
      </ProtectedRoute>
    );
    rerender(
      <ProtectedRoute>
        <div>secret</div>
      </ProtectedRoute>
    );

    await waitFor(() => expect(mockReplace).toHaveBeenCalled());
    expect(mockReplace).toHaveBeenCalledTimes(1);
  });
});
