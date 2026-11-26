import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Login from "./page";
import { AuthProvider, useAuth } from "@/lib/auth/AuthProvider";
import { apiClient } from "@/lib/api/apiClient";
import { AUTH_SESSION_QUERY_KEY } from "@/lib/auth/authSession";

// FVS-003 BATCH 4 Section C — this file exercises the REAL (unmocked)
// useLogin -> AuthProvider -> bootstrapAuthSession wiring together, with
// only apiClient mocked at the network boundary, specifically to prove the
// login->/me navigation race the batch instructions call out: the login
// page must not navigate while a destination's ProtectedRoute would still
// observe the old anonymous auth state. Every other login page test
// (page.test.tsx) mocks useLogin/useQueryClient directly and therefore
// cannot exercise whether a REAL queryClient.invalidateQueries() call
// actually waits for a real (possibly slow) /me refetch before resolving —
// that gap is exactly what this file closes.

const mockReplace = vi.fn();
let mockSearchParams = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: mockReplace }),
  useSearchParams: () => mockSearchParams,
}));

const SESSION_BODY = {
  user_id: "u-1",
  email: "ada@example.com",
  role: "customer",
  email_verified: true,
  session_expires_at: "2026-01-01T00:15:00Z",
};

const ME_BODY = {
  id: "u-1",
  email: "ada@example.com",
  role: "customer",
  email_verified: true,
  email_verified_at: "2025-01-01T00:00:00Z",
  created_at: "2024-01-01T00:00:00Z",
};

// A minimal, test-only stand-in for "whatever ProtectedRoute wraps" —
// never a real production route (per the batch's explicit instruction not
// to ship a throwaway protected page). It renders nothing but a plain
// projection of the exact same AuthProvider state ProtectedRoute itself
// would gate on, which is sufficient to prove the race.
function DestinationProbe() {
  const { isAuthenticated, isLoading } = useAuth();
  return (
    <div data-testid="destination">{isLoading ? "loading" : isAuthenticated ? "authenticated" : "anonymous"}</div>
  );
}

function renderApp(queryClient: QueryClient) {
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <Login />
        <DestinationProbe />
      </AuthProvider>
    </QueryClientProvider>
  );
}

async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/email/i), "ada@example.com");
  await user.type(screen.getByLabelText(/password/i), "correct-horse-battery");
  await user.click(screen.getByRole("button", { name: /log ?in/i }));
}

beforeEach(() => {
  mockReplace.mockReset();
  mockSearchParams = new URLSearchParams();
  // Start every test as a definitely-anonymous visitor: no csrf_token
  // cookie, matching real bootstrap step 1 ("zero network requests").
  document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/";
});

afterEach(() => {
  vi.restoreAllMocks();
  document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/";
});

describe("login -> /me navigation race (FVS-003 BATCH 4 Section C)", () => {
  it("does not navigate until the canonical /me refetch resolves authenticated, even when /me is intentionally delayed", async () => {
    const user = userEvent.setup();
    const queryClient = new QueryClient();

    let resolveMe!: (value: typeof ME_BODY) => void;
    const getSpy = vi.spyOn(apiClient, "get").mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveMe = resolve as (value: typeof ME_BODY) => void;
        })
    );
    vi.spyOn(apiClient, "post").mockImplementation(async () => {
      // Simulates the browser applying the backend's Set-Cookie response
      // for csrf_token immediately after a successful login — this is the
      // one piece of "the real browser would do this automatically" that
      // a mocked apiClient.post cannot do on its own.
      document.cookie = "csrf_token=test-value; path=/";
      return SESSION_BODY;
    });

    renderApp(queryClient);

    // 1. Initial auth state is anonymous, with zero /me calls (no cookie).
    await waitFor(() => expect(screen.getByTestId("destination")).toHaveTextContent("anonymous"));
    expect(getSpy).not.toHaveBeenCalled();

    // 2-3. POST /login succeeds; csrf_token becomes available.
    await fillAndSubmit(user);

    // 4. GET /me is intentionally delayed (still pending) — the navigation
    // and the destination's auth state must NOT have advanced yet.
    await waitFor(() => expect(getSpy).toHaveBeenCalledTimes(1));
    expect(mockReplace).not.toHaveBeenCalled();
    expect(queryClient.getQueryData(AUTH_SESSION_QUERY_KEY)).toBeNull();
    expect(screen.getByTestId("destination")).toHaveTextContent("anonymous");

    // 6-7. /me resolves authenticated — only now should navigation and the
    // canonical authenticated state settle.
    resolveMe(ME_BODY);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledTimes(1));
    expect(queryClient.getQueryData(AUTH_SESSION_QUERY_KEY)).toMatchObject({ id: "u-1" });
    expect(screen.getByTestId("destination")).toHaveTextContent("authenticated");
  });

  it("navigates to the safe returnTo only after the authenticated state has already settled", async () => {
    const user = userEvent.setup();
    const queryClient = new QueryClient();
    mockSearchParams = new URLSearchParams("returnTo=%2Faccount");

    vi.spyOn(apiClient, "get").mockResolvedValue(ME_BODY);
    vi.spyOn(apiClient, "post").mockImplementation(async () => {
      document.cookie = "csrf_token=test-value; path=/";
      return SESSION_BODY;
    });

    renderApp(queryClient);
    await waitFor(() => expect(screen.getByTestId("destination")).toHaveTextContent("anonymous"));

    await fillAndSubmit(user);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/account"));
    expect(queryClient.getQueryData(AUTH_SESSION_QUERY_KEY)).toMatchObject({ id: "u-1" });
  });
});
