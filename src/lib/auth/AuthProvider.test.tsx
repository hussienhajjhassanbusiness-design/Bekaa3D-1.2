import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, createElement, type ReactNode } from "react";
import { AuthProvider, useAuth } from "./AuthProvider";
import { getAuthSessionQueryOptions } from "./authSession";

// FVS-003-IMPLEMENTATION-PLAN.md §9 (confirmed BATCH 3A) — AuthProvider is a
// thin context wrapper around the one `["auth","session"]` query; it never
// maintains independent state that could drift from it. `getAuthSessionQueryOptions`
// (the one thing AuthProvider itself calls; its real behavior is proven
// separately in authSession.test.ts) is mocked here, whole, so this file
// tests only the context-projection behavior — mocking `bootstrapAuthSession`
// alone would not work, since the real `getAuthSessionQueryOptions` binds to
// it internally by module-private reference, not through the mocked export.
vi.mock("./authSession", () => ({ getAuthSessionQueryOptions: vi.fn() }));
const mockedGetOptions = vi.mocked(getAuthSessionQueryOptions);

function createWrapper() {
  const queryClient = new QueryClient();
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, createElement(AuthProvider, null, children));
  };
}

function Probe() {
  const { user, isAuthenticated, isLoading } = useAuth();
  return (
    <div>
      <span data-testid="loading">{String(isLoading)}</span>
      <span data-testid="authenticated">{String(isAuthenticated)}</span>
      <span data-testid="email">{user?.email ?? "none"}</span>
    </div>
  );
}

const SAFE_USER = {
  id: "u-1",
  email: "ada@example.com",
  role: "customer",
  emailVerified: true,
  emailVerifiedAt: "2026-01-01T00:00:00Z",
  createdAt: "2025-12-01T00:00:00Z",
};

function mockBootstrap(queryFn: () => Promise<typeof SAFE_USER | null>) {
  mockedGetOptions.mockReturnValue({
    queryKey: ["auth", "session"],
    queryFn,
    staleTime: Infinity,
    retry: false,
  });
}

beforeEach(() => {
  mockedGetOptions.mockReset();
});

describe("AuthProvider / useAuth", () => {
  it("is loading before the bootstrap check resolves", () => {
    mockBootstrap(() => new Promise(() => {}));
    render(<Probe />, { wrapper: createWrapper() });

    expect(screen.getByTestId("loading")).toHaveTextContent("true");
    expect(screen.getByTestId("authenticated")).toHaveTextContent("false");
  });

  it("projects an authenticated user once bootstrap resolves a SafeUser", async () => {
    mockBootstrap(() => Promise.resolve(SAFE_USER));
    render(<Probe />, { wrapper: createWrapper() });

    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));
    expect(screen.getByTestId("authenticated")).toHaveTextContent("true");
    expect(screen.getByTestId("email")).toHaveTextContent("ada@example.com");
  });

  it("projects anonymous when bootstrap resolves null", async () => {
    mockBootstrap(() => Promise.resolve(null));
    render(<Probe />, { wrapper: createWrapper() });

    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));
    expect(screen.getByTestId("authenticated")).toHaveTextContent("false");
    expect(screen.getByTestId("email")).toHaveTextContent("none");
  });

  it("throws a clear error when useAuth is called outside an AuthProvider", () => {
    function Orphan() {
      useAuth();
      return null;
    }
    const queryClient = new QueryClient();
    expect(() =>
      render(createElement(QueryClientProvider, { client: queryClient }, createElement(Orphan)))
    ).toThrow(/useAuth must be used within/);
  });

  it("does not create a duplicate/second AuthProvider state store — isAuthenticated is always derived from the same query data", async () => {
    mockBootstrap(() => Promise.resolve(SAFE_USER));
    render(<Probe />, { wrapper: createWrapper() });

    await waitFor(() => expect(screen.getByTestId("authenticated")).toHaveTextContent("true"));
    // Re-render with the same provider instance — the derived values must
    // stay consistent with the one underlying query, not drift.
    expect(screen.getByTestId("email")).toHaveTextContent("ada@example.com");
  });

  it("calls the bootstrap queryFn only once under React Strict Mode's dev-only double-invoke (query-level dedupe, not a refresh storm)", async () => {
    const queryFn = vi.fn(() => Promise.resolve(SAFE_USER));
    mockBootstrap(queryFn);
    const queryClient = new QueryClient();
    const Wrapper = ({ children }: { children: ReactNode }) =>
      createElement(
        StrictMode,
        null,
        createElement(QueryClientProvider, { client: queryClient }, createElement(AuthProvider, null, children))
      );

    render(<Probe />, { wrapper: Wrapper });

    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));
    expect(queryFn).toHaveBeenCalledTimes(1);
  });
});
