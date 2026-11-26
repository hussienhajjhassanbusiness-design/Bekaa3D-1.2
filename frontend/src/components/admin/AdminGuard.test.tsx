import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { act } from "react";
import { useAuth } from "@/lib/auth/AuthProvider";
import { notifyMfaRequired } from "@/lib/admin/mfaRequiredSignal";
import { AdminGuard } from "./AdminGuard";

// Phase 3 — P1-1 guard logic, matching the exact same shape as
// ProtectedRoute (loading/anonymous/isError handling) plus two
// admin-specific additions this slice owns:
//   1. A signed-in non-admin gets the real NotFoundContent, never an
//      "access denied, admin area exists here" page (no existence
//      leak — bekaa3d-api-contract's hiding-isn't-authorization rule
//      still means the backend independently refuses every admin call
//      regardless of what this component renders).
//   2. Any admin data hook's adminRequest() call that surfaces
//      MFA_REQUIRED notifies mfaRequiredSignal; AdminGuard is the one
//      place that turns that into a redirect to /admin/mfa/setup.
vi.mock("@/lib/auth/AuthProvider", () => ({ useAuth: vi.fn() }));
const mockedUseAuth = vi.mocked(useAuth);

const mockPush = vi.fn();
const mockReplace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
  usePathname: () => "/admin/settings",
}));

function authState(overrides: Partial<ReturnType<typeof useAuth>> = {}) {
  return {
    user: null,
    isAuthenticated: false,
    isLoading: false,
    isError: false,
    logout: vi.fn(),
    ...overrides,
  } as ReturnType<typeof useAuth>;
}

beforeEach(() => {
  mockPush.mockReset();
  mockReplace.mockReset();
  mockedUseAuth.mockReset();
});

describe("AdminGuard", () => {
  it("shows a loading state while the session is resolving, and renders no children", () => {
    mockedUseAuth.mockReturnValue(authState({ isLoading: true }));
    render(
      <AdminGuard>
        <div data-testid="admin-content">secret</div>
      </AdminGuard>
    );

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByTestId("admin-content")).toBeNull();
  });

  it("redirects a confirmed-anonymous visitor to /login with a returnTo of the current admin path", async () => {
    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: false, isLoading: false, isError: false }));
    render(
      <AdminGuard>
        <div data-testid="admin-content">secret</div>
      </AdminGuard>
    );

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login?returnTo=%2Fadmin%2Fsettings"));
    expect(screen.queryByTestId("admin-content")).toBeNull();
  });

  it("renders the real not-found page for a signed-in customer — never an admin-exists-here message", () => {
    mockedUseAuth.mockReturnValue(
      authState({
        isAuthenticated: true,
        user: { id: "u1", email: "c@example.com", role: "customer", emailVerified: true, emailVerifiedAt: null, createdAt: "x" },
      })
    );
    render(
      <AdminGuard>
        <div data-testid="admin-content">secret</div>
      </AdminGuard>
    );

    expect(screen.getByText(/404/)).toBeInTheDocument();
    expect(screen.queryByTestId("admin-content")).toBeNull();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("renders children for a signed-in administrator", () => {
    mockedUseAuth.mockReturnValue(
      authState({
        isAuthenticated: true,
        user: { id: "u1", email: "a@example.com", role: "admin", emailVerified: true, emailVerifiedAt: null, createdAt: "x" },
      })
    );
    render(
      <AdminGuard>
        <div data-testid="admin-content">secret</div>
      </AdminGuard>
    );

    expect(screen.getByTestId("admin-content")).toBeInTheDocument();
  });

  it("shows a retryable error state on a genuine transport failure, rather than guessing a role", () => {
    mockedUseAuth.mockReturnValue(authState({ isError: true }));
    render(
      <AdminGuard>
        <div data-testid="admin-content">secret</div>
      </AdminGuard>
    );

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByTestId("admin-content")).toBeNull();
  });

  it("redirects to /admin/mfa/setup when any admin data hook notifies mfaRequiredSignal", async () => {
    mockedUseAuth.mockReturnValue(
      authState({
        isAuthenticated: true,
        user: { id: "u1", email: "a@example.com", role: "admin", emailVerified: true, emailVerifiedAt: null, createdAt: "x" },
      })
    );
    render(
      <AdminGuard>
        <div data-testid="admin-content">secret</div>
      </AdminGuard>
    );

    act(() => {
      notifyMfaRequired();
    });

    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/admin/mfa/setup"));
  });
});
