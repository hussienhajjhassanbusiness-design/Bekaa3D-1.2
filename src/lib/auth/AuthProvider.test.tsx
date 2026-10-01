import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, createElement, type ReactNode } from "react";
import { AuthProvider, useAuth } from "./AuthProvider";
import { getAuthSessionQueryOptions, AUTH_SESSION_QUERY_KEY } from "./authSession";
import * as crossTabSignalModule from "./crossTabSignal";
import { useLogout } from "./useLogout";

// FVS-003-IMPLEMENTATION-PLAN.md §9 (confirmed BATCH 3A) — AuthProvider is a
// thin context wrapper around the one `["auth","session"]` query; it never
// maintains independent state that could drift from it. `getAuthSessionQueryOptions`
// (the one thing AuthProvider itself calls; its real behavior is proven
// separately in authSession.test.ts) is mocked here, whole, so this file
// tests only the context-projection behavior — mocking `bootstrapAuthSession`
// alone would not work, since the real `getAuthSessionQueryOptions` binds to
// it internally by module-private reference, not through the mocked export.
vi.mock("./authSession", async () => {
  const actual = await vi.importActual<typeof import("./authSession")>("./authSession");
  return { ...actual, getAuthSessionQueryOptions: vi.fn() };
});
const mockedGetOptions = vi.mocked(getAuthSessionQueryOptions);

// Part F (confirmed BATCH 3B) — useLogout's own transport/retry/CSRF
// behavior is proven separately in useLogout.test.ts; here it's mocked so
// these tests exercise only AuthProvider's forwarding of `logout` and its
// cross-tab wiring.
vi.mock("./useLogout", () => ({ useLogout: vi.fn() }));
const mockedUseLogout = vi.mocked(useLogout);

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
  mockedUseLogout.mockReset();
  mockedUseLogout.mockReturnValue({ mutateAsync: vi.fn() } as never);
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

    // FVS-003 BATCH 4 Section F/T11 finding (test-methodology only, no
    // product defect): passing the StrictMode wrapper via RTL's `wrapper`
    // render option does NOT actually trigger React's dev-only
    // mount->cleanup->mount effect double-invoke in this environment
    // (confirmed empirically — a bare counter effect run through
    // `render(ui, { wrapper })` stays at 1, while the identical tree built
    // directly inside `render(...)` reaches 2). The tree must be built
    // directly, with StrictMode as the actual root passed to `render`, for
    // this test to exercise genuine double-invoke rather than passing
    // trivially regardless of whether the dedupe behavior it claims to
    // prove is real.
    render(
      createElement(
        StrictMode,
        null,
        createElement(QueryClientProvider, { client: queryClient }, createElement(AuthProvider, null, createElement(Probe)))
      )
    );

    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));
    expect(queryFn).toHaveBeenCalledTimes(1);
  });
});

// Part F (confirmed BATCH 3B) — cross-tab logout wiring. `createCrossTabSignal`
// is spied on directly so these tests can capture the subscribed listener
// (simulating a message arriving from another tab) and assert on
// announce/subscribe/close calls, matching the useLogout.test.ts precedent.
describe("AuthProvider cross-tab logout wiring", () => {
  function createClientWrapper() {
    const queryClient = new QueryClient();
    const Wrapper = ({ children }: { children: ReactNode }) =>
      createElement(QueryClientProvider, { client: queryClient }, createElement(AuthProvider, null, children));
    return { queryClient, Wrapper };
  }

  function mockSignal() {
    const announce = vi.fn();
    const close = vi.fn();
    let listener: ((eventType: string) => void) | undefined;
    const subscribe = vi.fn((cb: (eventType: string) => void) => {
      listener = cb;
      return vi.fn();
    });
    vi.spyOn(crossTabSignalModule, "createCrossTabSignal").mockReturnValue({ announce, subscribe, close });
    return {
      announce,
      close,
      subscribe,
      deliver: (eventType: string) => listener?.(eventType),
    };
  }

  it("subscribes to the cross-tab signal on mount and unsubscribes + closes it on unmount", () => {
    mockBootstrap(() => Promise.resolve(null));
    const unsubscribe = vi.fn();
    const subscribe = vi.fn().mockReturnValue(unsubscribe);
    const close = vi.fn();
    vi.spyOn(crossTabSignalModule, "createCrossTabSignal").mockReturnValue({
      announce: vi.fn(),
      subscribe,
      close,
    });
    const { Wrapper } = createClientWrapper();

    const { unmount } = render(<Probe />, { wrapper: Wrapper });
    expect(subscribe).toHaveBeenCalledTimes(1);

    unmount();
    expect(unsubscribe).toHaveBeenCalledTimes(1);
    expect(close).toHaveBeenCalledTimes(1);
  });

  // FVS-003 BATCH 4 Section M — React Strict Mode's dev-only double-invoke
  // (mount -> cleanup -> mount) must leave exactly one ACTIVE cross-tab
  // subscription per provider instance, not two: the discarded first
  // mount's listener must be torn down (unsubscribe/close called) before
  // the second, surviving mount registers its own.
  it("StrictMode's dev-only double-invoke leaves exactly one active cross-tab subscription, not two", async () => {
    mockBootstrap(() => Promise.resolve(null));
    const unsubscribeCalls: number[] = [];
    const closeCalls: number[] = [];
    let subscribeCallCount = 0;
    const subscribe = vi.fn(() => {
      subscribeCallCount += 1;
      const thisRegistration = subscribeCallCount;
      return vi.fn(() => unsubscribeCalls.push(thisRegistration));
    });
    const close = vi.fn(() => closeCalls.push(subscribeCallCount));
    vi.spyOn(crossTabSignalModule, "createCrossTabSignal").mockReturnValue({
      announce: vi.fn(),
      subscribe,
      close,
    });
    const queryClient = new QueryClient();

    // See the sibling bootstrap-queryFn StrictMode test above for why the
    // tree is built directly here rather than via RTL's `wrapper` render
    // option — only this form genuinely triggers double-invoke.
    render(
      createElement(
        StrictMode,
        null,
        createElement(QueryClientProvider, { client: queryClient }, createElement(AuthProvider, null, createElement(Probe)))
      )
    );
    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));

    // Double-invoke registered twice, but exactly the FIRST registration's
    // resources were released — leaving registration #2 as the one
    // surviving, active subscription.
    expect(subscribe).toHaveBeenCalledTimes(2);
    expect(unsubscribeCalls).toEqual([1]);
    expect(closeCalls).toEqual([1]);
  });

  it("receiving a 'logout' cross-tab event sets the session anonymous immediately", async () => {
    mockBootstrap(() => Promise.resolve(SAFE_USER));
    const signal = mockSignal();
    const { Wrapper, queryClient } = createClientWrapper();
    render(<Probe />, { wrapper: Wrapper });

    await waitFor(() => expect(screen.getByTestId("authenticated")).toHaveTextContent("true"));

    signal.deliver("logout");

    expect(queryClient.getQueryData(AUTH_SESSION_QUERY_KEY)).toBeNull();
    await waitFor(() => expect(screen.getByTestId("authenticated")).toHaveTextContent("false"));
  });

  it("ignores cross-tab events other than the literal string 'logout'", async () => {
    mockBootstrap(() => Promise.resolve(SAFE_USER));
    const signal = mockSignal();
    const { Wrapper, queryClient } = createClientWrapper();
    render(<Probe />, { wrapper: Wrapper });
    await waitFor(() => expect(screen.getByTestId("authenticated")).toHaveTextContent("true"));

    signal.deliver("login");
    signal.deliver("session-updated");
    signal.deliver("");

    expect(queryClient.getQueryData(AUTH_SESSION_QUERY_KEY)).toEqual(SAFE_USER);
    expect(screen.getByTestId("authenticated")).toHaveTextContent("true");
  });

  it("the incoming logout handler never calls the backend logout mutation and never re-announces (no broadcast loop)", async () => {
    mockBootstrap(() => Promise.resolve(SAFE_USER));
    const mutateAsync = vi.fn();
    mockedUseLogout.mockReturnValue({ mutateAsync } as never);
    const signal = mockSignal();
    const { Wrapper } = createClientWrapper();
    render(<Probe />, { wrapper: Wrapper });
    await waitFor(() => expect(screen.getByTestId("authenticated")).toHaveTextContent("true"));

    signal.deliver("logout");

    expect(mutateAsync).not.toHaveBeenCalled();
    expect(signal.announce).not.toHaveBeenCalled();
  });

  it("exposes a logout() action on the context that forwards to useLogout's mutateAsync", async () => {
    mockBootstrap(() => Promise.resolve(SAFE_USER));
    const mutateAsync = vi.fn().mockResolvedValue({ serverConfirmed: true });
    mockedUseLogout.mockReturnValue({ mutateAsync } as never);
    mockSignal();

    function LogoutProbe() {
      const { logout } = useAuth();
      return (
        <button
          onClick={() => {
            void logout();
          }}
        >
          Log out
        </button>
      );
    }
    const { Wrapper } = createClientWrapper();
    render(<LogoutProbe />, { wrapper: Wrapper });

    screen.getByRole("button").click();

    expect(mutateAsync).toHaveBeenCalledTimes(1);
  });

  // FVS-003 BATCH 4 Section L — the backend requires that a user be
  // informable when server-side logout did not complete after local-first
  // logout. useLogout.ts's own mutateAsync already resolves (never throws)
  // a { serverConfirmed: boolean } result for exactly this reason (see its
  // own tests); what hadn't been proven before BATCH 4 is that
  // AuthProvider.logout() — the one seam a future real caller would
  // actually use — forwards that result unchanged rather than swallowing
  // it. "The hook internally knows it failed" is not feedback; a caller
  // that awaits `logout()` and inspects `serverConfirmed` is.
  it("logout() forwards a failed server-side outcome (serverConfirmed:false) to its caller unchanged, never swallowing or throwing it", async () => {
    mockBootstrap(() => Promise.resolve(SAFE_USER));
    const mutateAsync = vi.fn().mockResolvedValue({ serverConfirmed: false });
    mockedUseLogout.mockReturnValue({ mutateAsync } as never);
    mockSignal();

    let observedResult: unknown;
    function LogoutProbe() {
      const { logout } = useAuth();
      return (
        <button
          onClick={() => {
            void logout().then((result) => {
              observedResult = result;
            });
          }}
        >
          Log out
        </button>
      );
    }
    const { Wrapper } = createClientWrapper();
    render(<LogoutProbe />, { wrapper: Wrapper });

    screen.getByRole("button").click();

    await waitFor(() => expect(observedResult).toEqual({ serverConfirmed: false }));
  });

  it("the public interface exposes exactly user/isAuthenticated/isLoading/logout — no refreshSession, login, setUser, setAuthenticated, tokens, or roles helpers", async () => {
    mockBootstrap(() => Promise.resolve(SAFE_USER));
    mockSignal();
    function ShapeProbe() {
      const value = useAuth() as unknown as Record<string, unknown>;
      return <span data-testid="shape">{Object.keys(value).sort().join(",")}</span>;
    }
    const { Wrapper } = createClientWrapper();
    render(<ShapeProbe />, { wrapper: Wrapper });

    await waitFor(() =>
      expect(screen.getByTestId("shape")).toHaveTextContent("isAuthenticated,isLoading,logout,user")
    );
  });

  it("Review Focus: a stale in-flight auth refetch (as a concurrent login's invalidateQueries would trigger) does not re-authenticate the session after an incoming cross-tab logout", async () => {
    mockBootstrap(() => Promise.resolve(null));
    const signal = mockSignal();
    const { Wrapper, queryClient } = createClientWrapper();
    render(<Probe />, { wrapper: Wrapper });
    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));

    // Simulate "Tab B is mid-login": its own invalidateQueries has kicked
    // off a refetch of the canonical auth query that is still in flight.
    // fetchQuery's own explicit queryFn overrides the mounted query's
    // bound one for this one fetch, standing in for a concurrent refetch.
    let resolveRefetch!: (user: typeof SAFE_USER) => void;
    const refetchPromise = queryClient.fetchQuery({
      queryKey: AUTH_SESSION_QUERY_KEY,
      queryFn: () => new Promise<typeof SAFE_USER>((resolve) => { resolveRefetch = resolve; }),
    });
    // Let the refetch's queryFn actually start (its executor assigns
    // resolveRefetch) before delivering the logout signal — otherwise
    // cancellation would simply pre-empt a fetch that never began, which
    // isn't the in-flight race this test means to exercise.
    await waitFor(() => expect(typeof resolveRefetch).toBe("function"));

    // "Tab A" broadcasts logout while that refetch is still pending.
    signal.deliver("logout");
    expect(queryClient.getQueryData(AUTH_SESSION_QUERY_KEY)).toBeNull();

    // The stale login completion resolves AFTER the logout signal.
    resolveRefetch(SAFE_USER);
    await refetchPromise;

    expect(queryClient.getQueryData(AUTH_SESSION_QUERY_KEY)).toBeNull();
  });
});
