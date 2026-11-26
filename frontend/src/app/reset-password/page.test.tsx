import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ResetPassword from "./page";
import { usePasswordResetConfirm } from "@/lib/auth/usePasswordResetConfirm";

// Phase 2 auth/account batch — mounts FVS-004's confirm half. Mocks the
// hook (not apiClient/fetch), matching the existing page-test precedent.
// The reset link's confirmed format is `/reset-password#token=...` — the
// token lives in the URL FRAGMENT (location.hash), never a query param.

vi.mock("@/lib/auth/usePasswordResetConfirm", () => ({
  usePasswordResetConfirm: vi.fn(),
}));

const mockedUsePasswordResetConfirm = vi.mocked(usePasswordResetConfirm);

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: mockPush }),
}));

function setHash(hash: string) {
  window.history.replaceState(null, "", `/reset-password${hash}`);
}

function httpError(status: number, extra: Record<string, unknown> = {}) {
  return { kind: "http" as const, status, message: "x", raw: {}, ...extra };
}
function networkError() {
  return { kind: "network" as const, message: "We couldn't reach the server.", raw: undefined };
}
function timeoutError() {
  return { kind: "timeout" as const, message: "The server took too long to respond. Please try again.", raw: undefined };
}

async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>, password = "newpassword1") {
  await user.type(screen.getByLabelText(/new password/i), password);
  await user.click(screen.getByRole("button", { name: /reset password/i }));
}

beforeEach(() => {
  mockedUsePasswordResetConfirm.mockReset();
  mockPush.mockReset();
  setHash("#token=abc123");
});

afterEach(() => {
  window.history.replaceState(null, "", "/reset-password");
});

describe("ResetPassword (/reset-password)", () => {
  it("shows an invalid-link error state when there is no token in the hash, with a link to request a new one", () => {
    setHash("");
    mockedUsePasswordResetConfirm.mockReturnValue({ mutateAsync: vi.fn() } as never);
    render(<ResetPassword />);

    expect(screen.getByText(/invalid|expired/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /request a new/i })).toHaveAttribute("href", "/forgot-password");
    expect(screen.queryByLabelText(/new password/i)).toBeNull();
  });

  it("renders a new-password form when a token is present in the hash", () => {
    mockedUsePasswordResetConfirm.mockReturnValue({ mutateAsync: vi.fn() } as never);
    render(<ResetPassword />);

    expect(screen.getByLabelText(/new password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reset password/i })).toBeInTheDocument();
  });

  it("removes the token from the visible URL immediately after capturing it", () => {
    mockedUsePasswordResetConfirm.mockReturnValue({ mutateAsync: vi.fn() } as never);
    render(<ResetPassword />);

    expect(window.location.hash).toBe("");
    expect(window.location.href).not.toContain("abc123");
  });

  it("never logs the token anywhere", () => {
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    mockedUsePasswordResetConfirm.mockReturnValue({ mutateAsync: vi.fn() } as never);

    render(<ResetPassword />);

    for (const call of [...logSpy.mock.calls, ...errorSpy.mock.calls]) {
      expect(JSON.stringify(call)).not.toContain("abc123");
    }
    logSpy.mockRestore();
    errorSpy.mockRestore();
  });

  it("rejects a too-short password client-side without calling the mutation", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn();
    mockedUsePasswordResetConfirm.mockReturnValue({ mutateAsync } as never);
    render(<ResetPassword />);

    await fillAndSubmit(user, "short");

    await screen.findByRole("status");
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("submits { token, new_password } with the captured token on valid submit", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockedUsePasswordResetConfirm.mockReturnValue({ mutateAsync } as never);
    render(<ResetPassword />);

    await fillAndSubmit(user, "newpassword1");

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({ token: "abc123", new_password: "newpassword1" })
    );
  });

  it("on success shows a confirmation and a way to go to /login — never auto-authenticates", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockedUsePasswordResetConfirm.mockReturnValue({ mutateAsync } as never);
    render(<ResetPassword />);

    await fillAndSubmit(user);

    await screen.findByText(/password has been reset/i);
    expect(screen.queryByLabelText(/new password/i)).toBeNull();

    await user.click(screen.getByRole("button", { name: /log in/i }));
    expect(mockPush).toHaveBeenCalledWith("/login");
  });

  it("maps a 410 (expired token) to an expiry-specific safe message with a link to request a new one", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue(httpError(410));
    mockedUsePasswordResetConfirm.mockReturnValue({ mutateAsync } as never);
    render(<ResetPassword />);

    await fillAndSubmit(user);

    expect(await screen.findByText(/expired/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /request a new/i })).toHaveAttribute("href", "/forgot-password");
  });

  it("maps a 422 validation error on new_password (via errors[].loc, dropping loc[0]) to its specific safe message — the form stays visible for retry, not the dead-link state", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue(
      httpError(422, {
        errors: [{ loc: ["body", "new_password"], msg: "backend diagnostic text never shown", type: "string_too_short" }],
      })
    );
    mockedUsePasswordResetConfirm.mockReturnValue({ mutateAsync } as never);
    render(<ResetPassword />);

    await fillAndSubmit(user);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This value is too short.");
    expect(alert).not.toHaveTextContent(/backend diagnostic text never shown/i);
    // Unlike a dead/used link, a 422 lets the user fix the form and retry.
    expect(screen.getByLabelText(/new password/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /request a new/i })).toBeNull();
  });

  it("maps a 400 (token unknown/used/account unusable) to an invalid-link safe message", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue(httpError(400));
    mockedUsePasswordResetConfirm.mockReturnValue({ mutateAsync } as never);
    render(<ResetPassword />);

    await fillAndSubmit(user);

    expect(await screen.findByText(/invalid|already been used/i)).toBeInTheDocument();
  });

  it("maps a 429 to a rate-limit-specific message", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue(httpError(429));
    mockedUsePasswordResetConfirm.mockReturnValue({ mutateAsync } as never);
    render(<ResetPassword />);

    await fillAndSubmit(user);

    expect(await screen.findByRole("alert")).toHaveTextContent(/too many/i);
  });

  it("shows a safe alert on a network failure", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue(networkError());
    mockedUsePasswordResetConfirm.mockReturnValue({ mutateAsync } as never);
    render(<ResetPassword />);

    await fillAndSubmit(user);

    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't reach|try again/i);
  });

  it("shows a safe alert on a timeout failure", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue(timeoutError());
    mockedUsePasswordResetConfirm.mockReturnValue({ mutateAsync } as never);
    render(<ResetPassword />);

    await fillAndSubmit(user);

    expect(await screen.findByRole("alert")).toHaveTextContent(/took too long|try again/i);
  });

  it("shows a safe generic alert on an unrecognized HTTP failure, never rendering ApiError.raw", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue({
      kind: "http",
      status: 500,
      message: "x",
      raw: { title: "SECRET_RAW_DIAGNOSTIC_TEXT" },
    });
    mockedUsePasswordResetConfirm.mockReturnValue({ mutateAsync } as never);
    render(<ResetPassword />);

    await fillAndSubmit(user);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/something went wrong|try again/i);
    expect(screen.queryByText(/SECRET_RAW_DIAGNOSTIC_TEXT/)).toBeNull();
  });
});

// Phase 5A defect 6 — the real hydration mismatch, reproduced in Edge
// against the dev server: the token lives only in the URL fragment, which
// never reaches the server, so the server always rendered the
// invalid-link alert while the client's first render (a useState
// initializer reading window.location.hash) rendered the form. These
// tests hydrate genuine server markup (renderToString, produced without a
// fragment exactly as the server sees the request) and fail on any
// recoverable hydration error.
describe("ResetPassword hydration (Phase 5A defect 6)", () => {
  const cleanups: (() => void)[] = [];
  afterEach(() => {
    while (cleanups.length) cleanups.pop()?.();
  });

  async function hydrateServerMarkup(clientHash: string) {
    const { renderToString } = await import("react-dom/server");
    const { hydrateRoot } = await import("react-dom/client");
    const { act } = await import("react");
    mockedUsePasswordResetConfirm.mockReturnValue({ mutateAsync: vi.fn() } as never);

    setHash("");
    const serverHtml = renderToString(<ResetPassword />);

    setHash(clientHash);
    const container = document.createElement("div");
    container.innerHTML = serverHtml;
    document.body.appendChild(container);
    const recoverableErrors: unknown[] = [];
    let root: ReturnType<typeof hydrateRoot> | undefined;
    await act(async () => {
      root = hydrateRoot(container, <ResetPassword />, {
        onRecoverableError: (error) => recoverableErrors.push(error),
      });
    });
    cleanups.push(() => {
      act(() => root?.unmount());
      container.remove();
    });
    return { serverHtml, container, recoverableErrors };
  }

  it("server markup is the neutral pending state — never the invalid-link alert it cannot know is true", async () => {
    const { serverHtml } = await hydrateServerMarkup("#token=abc123");
    expect(serverHtml).not.toMatch(/invalid, expired, or missing a token/);
    expect(serverHtml).not.toMatch(/New password/);
  });

  it("hydrates a #token= link with no hydration error, then shows the form and clears the fragment", async () => {
    const { container, recoverableErrors } = await hydrateServerMarkup("#token=abc123");
    expect(recoverableErrors).toEqual([]);
    expect(container.querySelector("input[type='password']")).not.toBeNull();
    expect(window.location.hash).toBe("");
    expect(window.location.href).not.toContain("abc123");
  });

  it("hydrates a link with no token with no hydration error, then shows the invalid-link state", async () => {
    const { container, recoverableErrors } = await hydrateServerMarkup("");
    expect(recoverableErrors).toEqual([]);
    expect(container.textContent).toMatch(/invalid, expired, or missing a token/);
  });

  it("keeps the captured token under React Strict Mode's double effect run (the fragment is already gone on the second run)", async () => {
    const { StrictMode } = await import("react");
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockedUsePasswordResetConfirm.mockReturnValue({ mutateAsync } as never);
    const user = userEvent.setup();
    render(
      <StrictMode>
        <ResetPassword />
      </StrictMode>
    );

    await fillAndSubmit(user, "newpassword1");
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ token: "abc123", new_password: "newpassword1" }));
  });
});

// Redesign Batch 4 — the auth card must not change where the token lives.
describe("ResetPassword (/reset-password) — Batch 4 auth card", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it("never renders the token or writes it to browser storage, before or after a submit", async () => {
    const user = userEvent.setup();
    setHash("#token=TOKEN_SECRET_VALUE_123");
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockedUsePasswordResetConfirm.mockReturnValue({ mutateAsync } as never);
    const setItem = vi.spyOn(Storage.prototype, "setItem");

    render(<ResetPassword />);
    expect(document.body.innerHTML).not.toContain("TOKEN_SECRET_VALUE_123");

    await fillAndSubmit(user);
    await screen.findByText(/password has been reset/i);

    expect(mutateAsync).toHaveBeenCalledWith({ token: "TOKEN_SECRET_VALUE_123", new_password: "newpassword1" });
    expect(document.body.innerHTML).not.toContain("TOKEN_SECRET_VALUE_123");
    expect(window.location.href).not.toContain("TOKEN_SECRET_VALUE_123");
    for (const call of setItem.mock.calls) {
      expect(JSON.stringify(call)).not.toContain("TOKEN_SECRET_VALUE_123");
    }
    expect(JSON.stringify({ ...window.localStorage, ...window.sessionStorage })).not.toContain("TOKEN_SECRET_VALUE_123");
    setItem.mockRestore();
  });

  it("keeps one h1 in every state and offers a way back to log in from the form", () => {
    mockedUsePasswordResetConfirm.mockReturnValue({ mutateAsync: vi.fn() } as never);
    render(<ResetPassword />);

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("link", { name: /back to log in/i })).toHaveAttribute("href", "/login");
  });
});
