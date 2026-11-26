import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useQueryClient } from "@tanstack/react-query";
import { ProfileCard } from "./ProfileCard";
import { useAuth, type AuthContextValue } from "@/lib/auth/AuthProvider";
import { AUTH_SESSION_QUERY_KEY, type SafeUser } from "@/lib/auth/authSession";

// FVS-006-IMPLEMENTATION-PLAN.md T03 — read-only profile display. Reads
// useAuth() directly (no second /me fetch anywhere in this file). No
// edit/save/cancel control of any kind is ever rendered — VS-006 is
// deliberately read-only.

vi.mock("@/lib/auth/AuthProvider", () => ({ useAuth: vi.fn() }));
const mockedUseAuth = vi.mocked(useAuth);

vi.mock("@tanstack/react-query", async () => {
  const actual = await vi.importActual<typeof import("@tanstack/react-query")>("@tanstack/react-query");
  return { ...actual, useQueryClient: vi.fn() };
});
const mockedUseQueryClient = vi.mocked(useQueryClient);

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

const VERIFIED_USER: SafeUser = {
  id: "u-1",
  email: "ada@example.com",
  role: "customer",
  emailVerified: true,
  emailVerifiedAt: "2026-01-01T00:00:00Z",
  createdAt: "2025-12-01T00:00:00Z",
};

const UNVERIFIED_USER: SafeUser = { ...VERIFIED_USER, emailVerified: false, emailVerifiedAt: null };

let refetchQueries: ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockedUseAuth.mockReset();
  refetchQueries = vi.fn().mockResolvedValue(undefined);
  mockedUseQueryClient.mockReturnValue({ refetchQueries } as never);
});

describe("ProfileCard", () => {
  it("renders the user's email", () => {
    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true, user: VERIFIED_USER }));
    render(<ProfileCard />);

    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
  });

  it("shows a human-readable verified status", () => {
    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true, user: VERIFIED_USER }));
    render(<ProfileCard />);

    expect(screen.getByText(/verified/i)).toBeInTheDocument();
  });

  it("shows a human-readable unverified status and a banner when email_verified is false", () => {
    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true, user: UNVERIFIED_USER }));
    render(<ProfileCard />);

    expect(screen.getByText(/not verified/i)).toBeInTheDocument();
    expect(screen.getByText(/isn.t verified yet/i)).toBeInTheDocument();
  });

  it("the unverified banner links to the existing FVS-002 resend route, never a new one", () => {
    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true, user: UNVERIFIED_USER }));
    render(<ProfileCard />);

    expect(screen.getByRole("link", { name: /resend/i })).toHaveAttribute("href", "/verify-email/resend");
  });

  it("the unverified banner is absent entirely when the email is verified", () => {
    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true, user: VERIFIED_USER }));
    render(<ProfileCard />);

    expect(screen.queryByRole("link", { name: /resend/i })).not.toBeInTheDocument();
  });

  it("shows a loading skeleton while the auth query is loading", () => {
    mockedUseAuth.mockReturnValue(authState({ isLoading: true }));
    render(<ProfileCard />);

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByText("ada@example.com")).not.toBeInTheDocument();
  });

  it("shows a safe error message and a Retry button when the auth query errors", () => {
    mockedUseAuth.mockReturnValue(authState({ isError: true }));
    render(<ProfileCard />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("never renders raw ApiError diagnostic content on an error", () => {
    mockedUseAuth.mockReturnValue(authState({ isError: true }));
    render(<ProfileCard />);

    const bodyText = document.body.textContent ?? "";
    expect(bodyText).not.toMatch(/ApiError|stack|detail:/i);
  });

  it("retry re-triggers the canonical auth query — the exact AUTH_SESSION_QUERY_KEY, never a new fetch path", async () => {
    mockedUseAuth.mockReturnValue(authState({ isError: true }));
    const user = userEvent.setup();
    render(<ProfileCard />);

    await user.click(screen.getByRole("button", { name: /retry/i }));

    expect(refetchQueries).toHaveBeenCalledWith({ queryKey: AUTH_SESSION_QUERY_KEY });
  });

  it("disables the Retry button and marks it busy while a retry is in flight, so it can't be mashed repeatedly", async () => {
    let resolveRefetch!: () => void;
    refetchQueries.mockReturnValue(
      new Promise<void>((resolve) => {
        resolveRefetch = resolve;
      })
    );
    mockedUseAuth.mockReturnValue(authState({ isError: true }));
    const user = userEvent.setup();
    render(<ProfileCard />);

    const retryButton = screen.getByRole("button", { name: /retry/i });
    await user.click(retryButton);

    expect(retryButton).toBeDisabled();
    expect(retryButton).toHaveAttribute("aria-busy", "true");
    expect(refetchQueries).toHaveBeenCalledTimes(1);

    // A second click while still in flight must not fire a second refetch.
    await user.click(retryButton);
    expect(refetchQueries).toHaveBeenCalledTimes(1);

    resolveRefetch();
    await waitFor(() => expect(retryButton).not.toBeDisabled());
  });

  it("renders no editable input of any kind", () => {
    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true, user: VERIFIED_USER }));
    render(<ProfileCard />);

    expect(document.querySelectorAll("input, textarea, select")).toHaveLength(0);
  });

  it("renders no Save/Edit/Cancel control of any kind", () => {
    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true, user: VERIFIED_USER }));
    render(<ProfileCard />);

    expect(screen.queryByRole("button", { name: /save/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /cancel/i })).not.toBeInTheDocument();
  });

  describe("Batch 5 layout", () => {
    it("keeps exactly one h1 'Profile' in the loading, error and loaded states", () => {
      for (const state of [
        { isLoading: true },
        { isError: true },
        { isAuthenticated: true, user: VERIFIED_USER },
      ] as const) {
        mockedUseAuth.mockReturnValue(authState(state));
        const { unmount } = render(<ProfileCard />);
        expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
        expect(screen.getByRole("heading", { level: 1, name: "Profile" })).toBeInTheDocument();
        unmount();
      }
    });

    it("shows 'Member since' from the real createdAt, and hides it for an unparsable value", () => {
      mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true, user: VERIFIED_USER }));
      const { unmount } = render(<ProfileCard />);
      expect(screen.getByText("Member since December 2025")).toBeInTheDocument();
      unmount();

      mockedUseAuth.mockReturnValue(
        authState({ isAuthenticated: true, user: { ...VERIFIED_USER, createdAt: "not-a-date" } })
      );
      render(<ProfileCard />);
      expect(screen.queryByText(/member since/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/invalid date/i)).not.toBeInTheDocument();
    });

    it("renders the email once and the status rows as term/definition pairs under an 'Account details' h2", () => {
      mockedUseAuth.mockReturnValue(authState({ isAuthenticated: true, user: VERIFIED_USER }));
      render(<ProfileCard />);
      expect(screen.getAllByText("ada@example.com")).toHaveLength(1);
      expect(screen.getByRole("heading", { level: 2, name: "Account details" })).toBeInTheDocument();
      expect(screen.getByText("Verification status").tagName).toBe("DT");
      expect(screen.getByText("Account status").tagName).toBe("DT");
    });
  });
});
