import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useQueryClient } from "@tanstack/react-query";
import Login from "./page";
import { useLogin } from "@/lib/auth/useLogin";
import { useMfaVerify } from "@/lib/auth/useMfaVerify";

// FVS-003-IMPLEMENTATION-PLAN.md §2/Part C (confirmed BATCH 3B) — mocks
// useLogin (the hook, not apiClient/fetch) and next/navigation, matching
// the FVS-002 page-test precedent of mocking the owning hook. useLogin's
// own transport wiring is proven separately in useLogin.test.ts; this file
// tests validation/UX/MFA-safety/enumeration-safety/returnTo behavior.

vi.mock("@/lib/auth/useLogin", () => ({ useLogin: vi.fn() }));
const mockedUseLogin = vi.mocked(useLogin);

// Phase 3 (FVS-005) — real admin MFA verify step. Mocked the same way as
// useLogin; useMfaVerify's own transport wiring is proven separately in
// useMfaVerify.test.ts.
vi.mock("@/lib/auth/useMfaVerify", () => ({ useMfaVerify: vi.fn() }));
const mockedUseMfaVerify = vi.mocked(useMfaVerify);

const mockPush = vi.fn();
const mockReplace = vi.fn();
let mockSearchParams = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
  useSearchParams: () => mockSearchParams,
}));

vi.mock("@tanstack/react-query", async () => {
  const actual = await vi.importActual<typeof import("@tanstack/react-query")>("@tanstack/react-query");
  return { ...actual, useQueryClient: vi.fn() };
});
const mockedUseQueryClient = vi.mocked(useQueryClient);

function networkError() {
  return { kind: "network" as const, message: "We couldn't reach the server.", raw: undefined };
}
function timeoutError() {
  return { kind: "timeout" as const, message: "The server took too long to respond. Please try again.", raw: undefined };
}
function httpError(status: number, code?: string, extra: Record<string, unknown> = {}) {
  return { kind: "http" as const, status, code, message: "x", raw: undefined, ...extra };
}

async function fillValidForm(user: ReturnType<typeof userEvent.setup>, email = "ada@example.com") {
  await user.type(screen.getByLabelText(/email/i), email);
  await user.type(screen.getByLabelText(/password/i), "whatever-password");
}

let invalidateQueries: ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockedUseLogin.mockReset();
  mockedUseMfaVerify.mockReturnValue({ mutateAsync: vi.fn() } as never);
  mockPush.mockReset();
  mockReplace.mockReset();
  mockSearchParams = new URLSearchParams();
  invalidateQueries = vi.fn().mockResolvedValue(undefined);
  mockedUseQueryClient.mockReturnValue({ invalidateQueries } as never);
});

describe("Login (/login)", () => {
  it("renders labeled email and password fields and a submit button", () => {
    mockedUseLogin.mockReturnValue({ mutateAsync: vi.fn() } as never);
    render(<Login />);

    expect(screen.getByRole("heading", { name: /log ?in|sign ?in/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /log ?in|sign ?in/i })).toBeInTheDocument();
  });

  it("password show/hide toggle is present and preserves the typed value", async () => {
    const user = userEvent.setup();
    mockedUseLogin.mockReturnValue({ mutateAsync: vi.fn() } as never);
    render(<Login />);

    await user.type(screen.getByLabelText(/password/i), "secret-value");
    await user.click(screen.getByRole("button", { name: /show password/i }));

    expect(screen.getByLabelText(/password/i)).toHaveAttribute("type", "text");
    expect(screen.getByLabelText(/password/i)).toHaveValue("secret-value");
  });

  it("rejects an empty email client-side without calling the mutation", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn();
    mockedUseLogin.mockReturnValue({ mutateAsync } as never);
    render(<Login />);

    await user.type(screen.getByLabelText(/password/i), "whatever-password");
    await user.click(screen.getByRole("button", { name: /log ?in|sign ?in/i }));

    await screen.findByRole("status");
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("rejects a malformed email client-side without calling the mutation", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn();
    mockedUseLogin.mockReturnValue({ mutateAsync } as never);
    render(<Login />);

    await user.type(screen.getByLabelText(/email/i), "not-an-email");
    await user.type(screen.getByLabelText(/password/i), "whatever-password");
    await user.click(screen.getByRole("button", { name: /log ?in|sign ?in/i }));

    await screen.findByRole("status");
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("rejects an empty password client-side without calling the mutation", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn();
    mockedUseLogin.mockReturnValue({ mutateAsync } as never);
    render(<Login />);

    await user.type(screen.getByLabelText(/email/i), "ada@example.com");
    await user.click(screen.getByRole("button", { name: /log ?in|sign ?in/i }));

    await screen.findByRole("status");
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("trims the email before submission", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ kind: "session", data: {} });
    mockedUseLogin.mockReturnValue({ mutateAsync } as never);
    render(<Login />);

    await user.type(screen.getByLabelText(/email/i), "  ada@example.com  ");
    await user.type(screen.getByLabelText(/password/i), "whatever-password");
    await user.click(screen.getByRole("button", { name: /log ?in|sign ?in/i }));

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({ email: "ada@example.com", password: "whatever-password" })
    );
  });

  it("does NOT trim the password before submission", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ kind: "session", data: {} });
    mockedUseLogin.mockReturnValue({ mutateAsync } as never);
    render(<Login />);

    await user.type(screen.getByLabelText(/email/i), "ada@example.com");
    await user.click(screen.getByLabelText(/password/i));
    await user.paste(" correct horse battery ");
    await user.click(screen.getByRole("button", { name: /log ?in|sign ?in/i }));

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({
        email: "ada@example.com",
        password: " correct horse battery ",
      })
    );
  });

  it("does not enforce registration's 8-character password minimum — a short pre-existing password is accepted client-side", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ kind: "session", data: {} });
    mockedUseLogin.mockReturnValue({ mutateAsync } as never);
    render(<Login />);

    await user.type(screen.getByLabelText(/email/i), "ada@example.com");
    await user.type(screen.getByLabelText(/password/i), "short1");
    await user.click(screen.getByRole("button", { name: /log ?in|sign ?in/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
  });

  it("submits the exact request body on a valid submit", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ kind: "session", data: {} });
    mockedUseLogin.mockReturnValue({ mutateAsync } as never);
    render(<Login />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /log ?in|sign ?in/i }));

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({ email: "ada@example.com", password: "whatever-password" })
    );
  });

  it("on a 200 session result, invalidates the canonical auth query before navigating to the safe returnTo", async () => {
    const user = userEvent.setup();
    mockSearchParams = new URLSearchParams("returnTo=%2Faccount");
    const mutateAsync = vi.fn().mockResolvedValue({ kind: "session", data: { user_id: "u1" } });
    mockedUseLogin.mockReturnValue({ mutateAsync } as never);
    render(<Login />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /log ?in|sign ?in/i }));

    await waitFor(() => expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["auth", "session"] }));
    await waitFor(() => expect(mockReplace.mock.calls.length + mockPush.mock.calls.length).toBeGreaterThan(0));
    const navigatedTo = (mockReplace.mock.calls[0] ?? mockPush.mock.calls[0])?.[0];
    expect(navigatedTo).toBe("/account");
  });

  it("falls back to / for a missing returnTo", async () => {
    const user = userEvent.setup();
    mockSearchParams = new URLSearchParams();
    const mutateAsync = vi.fn().mockResolvedValue({ kind: "session", data: {} });
    mockedUseLogin.mockReturnValue({ mutateAsync } as never);
    render(<Login />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /log ?in|sign ?in/i }));

    await waitFor(() => expect(mockReplace.mock.calls.length + mockPush.mock.calls.length).toBeGreaterThan(0));
    const navigatedTo = (mockReplace.mock.calls[0] ?? mockPush.mock.calls[0])?.[0];
    expect(navigatedTo).toBe("/");
  });

  it("falls back to / for an unsafe (open-redirect) returnTo, never honoring it", async () => {
    const user = userEvent.setup();
    mockSearchParams = new URLSearchParams("returnTo=https%3A%2F%2Fevil.example");
    const mutateAsync = vi.fn().mockResolvedValue({ kind: "session", data: {} });
    mockedUseLogin.mockReturnValue({ mutateAsync } as never);
    render(<Login />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /log ?in|sign ?in/i }));

    await waitFor(() => expect(mockReplace.mock.calls.length + mockPush.mock.calls.length).toBeGreaterThan(0));
    const navigatedTo = (mockReplace.mock.calls[0] ?? mockPush.mock.calls[0])?.[0];
    expect(navigatedTo).toBe("/");
  });

  it("401 INVALID_CREDENTIALS shows the exact generic copy 'Invalid email or password.'", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue(httpError(401, "INVALID_CREDENTIALS"));
    mockedUseLogin.mockReturnValue({ mutateAsync } as never);
    render(<Login />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /log ?in|sign ?in/i }));

    expect(await screen.findByText("Invalid email or password.")).toBeInTheDocument();
  });

  it("renders identical copy for an unknown-email scenario and a wrong-password scenario — both are INVALID_CREDENTIALS and must never be distinguished", async () => {
    const user = userEvent.setup();

    const mutateAsyncUnknown = vi.fn().mockRejectedValue(httpError(401, "INVALID_CREDENTIALS"));
    mockedUseLogin.mockReturnValue({ mutateAsync: mutateAsyncUnknown } as never);
    const { unmount } = render(<Login />);
    await fillValidForm(user, "unknown@example.com");
    await user.click(screen.getByRole("button", { name: /log ?in|sign ?in/i }));
    const unknownCopy = (await screen.findByText("Invalid email or password.")).textContent;
    unmount();

    const mutateAsyncWrongPassword = vi.fn().mockRejectedValue(httpError(401, "INVALID_CREDENTIALS"));
    mockedUseLogin.mockReturnValue({ mutateAsync: mutateAsyncWrongPassword } as never);
    render(<Login />);
    await fillValidForm(user, "existing@example.com");
    await user.click(screen.getByRole("button", { name: /log ?in|sign ?in/i }));
    const wrongPasswordCopy = (await screen.findByText("Invalid email or password.")).textContent;

    expect(unknownCopy).toBe(wrongPasswordCopy);
  });

  it("403 ACCOUNT_DISABLED shows safe generic copy, never revealing that the password was correct", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue(httpError(403, "ACCOUNT_DISABLED"));
    mockedUseLogin.mockReturnValue({ mutateAsync } as never);
    render(<Login />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /log ?in|sign ?in/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/unable to sign in/i);
    expect(alert).not.toHaveTextContent(/disabled|correct password/i);
  });

  it("429 RATE_LIMITED shows safe generic rate-limit copy without revealing attempt counts or thresholds", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue(httpError(429, "RATE_LIMITED", { retryAfterSeconds: 60 }));
    mockedUseLogin.mockReturnValue({ mutateAsync } as never);
    render(<Login />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /log ?in|sign ?in/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/too many|wait/i);
    // "Too many attempts" is itself the established safe phrase (matches
    // FVS-002's own rate-limit copy) — what must never appear is a specific
    // failed-attempt COUNT or lockout THRESHOLD number, which this message
    // template never references at all.
    expect(alert.textContent).not.toMatch(/\d+\s*(failed )?attempts?\b/i);
    expect(alert.textContent).not.toMatch(/threshold/i);
  });

  it("a network failure shows a safe message", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue(networkError());
    mockedUseLogin.mockReturnValue({ mutateAsync } as never);
    render(<Login />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /log ?in|sign ?in/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/couldn't reach|try again/i);
  });

  it("a timeout failure shows a safe message", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue(timeoutError());
    mockedUseLogin.mockReturnValue({ mutateAsync } as never);
    render(<Login />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /log ?in|sign ?in/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/took too long|try again/i);
  });

  it("never renders raw diagnostic content from a failure", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue({
      kind: "http",
      status: 401,
      code: "INVALID_CREDENTIALS",
      message: "x",
      raw: { title: "SECRET_RAW_DIAGNOSTIC_TEXT" },
    });
    mockedUseLogin.mockReturnValue({ mutateAsync } as never);
    render(<Login />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /log ?in|sign ?in/i }));

    await screen.findByRole("alert");
    expect(screen.queryByText(/SECRET_RAW_DIAGNOSTIC_TEXT/)).toBeNull();
  });

  it("prevents a rapid double submission from firing the mutation twice", async () => {
    const user = userEvent.setup();
    let resolveMutate!: (value: unknown) => void;
    const mutateAsync = vi.fn(() => new Promise((resolve) => { resolveMutate = resolve; }));
    mockedUseLogin.mockReturnValue({ mutateAsync } as never);
    render(<Login />);

    await fillValidForm(user);
    const submitButton = screen.getByRole("button", { name: /log ?in|sign ?in/i });
    await user.click(submitButton);
    await user.click(submitButton);

    resolveMutate({ kind: "session", data: {} });
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
  });

  it("202 MFA challenge does not mark AuthProvider authenticated — the canonical auth query is never invalidated", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({
      kind: "mfaChallenge",
      data: { challenge_id: "secret-challenge-id", expires_in_seconds: 300 },
    });
    mockedUseLogin.mockReturnValue({ mutateAsync } as never);
    render(<Login />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /log ?in|sign ?in/i }));

    await screen.findByText(/verification|not yet available/i);
    expect(invalidateQueries).not.toHaveBeenCalled();
  });

  it("202 MFA challenge never exposes challenge_id anywhere in the rendered page", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({
      kind: "mfaChallenge",
      data: { challenge_id: "secret-challenge-id", expires_in_seconds: 300 },
    });
    mockedUseLogin.mockReturnValue({ mutateAsync } as never);
    render(<Login />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /log ?in|sign ?in/i }));

    await screen.findByText(/verification|not yet available/i);
    expect(screen.queryByText(/secret-challenge-id/)).toBeNull();
  });

  it("202 MFA challenge does not navigate anywhere", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({
      kind: "mfaChallenge",
      data: { challenge_id: "c1", expires_in_seconds: 300 },
    });
    mockedUseLogin.mockReturnValue({ mutateAsync } as never);
    render(<Login />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /log ?in|sign ?in/i }));

    await screen.findByText(/verification|not yet available/i);
    expect(mockPush).not.toHaveBeenCalled();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("sends no CSRF option and never triggers refresh behavior on failure (login mutation is called with just the credentials)", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue(httpError(401, "INVALID_CREDENTIALS"));
    mockedUseLogin.mockReturnValue({ mutateAsync } as never);
    render(<Login />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /log ?in|sign ?in/i }));

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({ email: "ada@example.com", password: "whatever-password" })
    );
  });

  it("the primary submit CTA is full-width, per the plan's mobile/desktop full-width-CTA requirement", () => {
    mockedUseLogin.mockReturnValue({ mutateAsync: vi.fn() } as never);
    render(<Login />);

    expect(screen.getByRole("button", { name: /log ?in|sign ?in/i })).toHaveClass("w-full");
  });
});

// Phase 3 (FVS-005/P1-2) — the real MFA verify step, replacing the old
// "not available yet" placeholder. challenge_id must stay in memory
// only (never rendered, never in a URL/storage), a wrong code or an
// expired challenge must force a fresh login (never a retry against the
// same challenge_id), and success must follow the exact same
// invalidate-then-navigate sequence as a direct 200 session login.
describe("Login (/login) — MFA verification step", () => {
  async function reachMfaStep(user: ReturnType<typeof userEvent.setup>, expiresInSeconds = 300) {
    const loginMutateAsync = vi.fn().mockResolvedValue({
      kind: "mfaChallenge",
      data: { challenge_id: "secret-challenge-id", expires_in_seconds: expiresInSeconds },
    });
    mockedUseLogin.mockReturnValue({ mutateAsync: loginMutateAsync } as never);
    render(<Login />);
    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /log ?in|sign ?in/i }));
    await screen.findByLabelText(/verification code/i);
  }

  it("renders a verification-code field and submit button once the challenge arrives", async () => {
    const user = userEvent.setup();
    await reachMfaStep(user);

    expect(screen.getByLabelText(/verification code/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /verify/i })).toBeInTheDocument();
  });

  it("submits the challenge_id and entered code, then invalidates the auth session and navigates on success", async () => {
    const user = userEvent.setup();
    const verifyMutateAsync = vi.fn().mockResolvedValue(undefined);
    mockedUseMfaVerify.mockReturnValue({ mutateAsync: verifyMutateAsync } as never);
    await reachMfaStep(user);

    await user.type(screen.getByLabelText(/verification code/i), "123456");
    await user.click(screen.getByRole("button", { name: /verify/i }));

    await waitFor(() =>
      expect(verifyMutateAsync).toHaveBeenCalledWith({ challenge_id: "secret-challenge-id", code: "123456" })
    );
    await waitFor(() => expect(invalidateQueries).toHaveBeenCalledTimes(1));
    expect(mockReplace).toHaveBeenCalledWith("/");
  });

  it("toggling to 'use a recovery code' sends recovery_code instead of code", async () => {
    const user = userEvent.setup();
    const verifyMutateAsync = vi.fn().mockResolvedValue(undefined);
    mockedUseMfaVerify.mockReturnValue({ mutateAsync: verifyMutateAsync } as never);
    await reachMfaStep(user);

    await user.click(screen.getByRole("button", { name: /use a recovery code/i }));
    await user.type(screen.getByLabelText(/recovery code/i), "abcd-efgh");
    await user.click(screen.getByRole("button", { name: /verify/i }));

    await waitFor(() =>
      expect(verifyMutateAsync).toHaveBeenCalledWith({ challenge_id: "secret-challenge-id", recovery_code: "abcd-efgh" })
    );
  });

  it("on MFA_INVALID, shows a safe message and returns to the login form — the burned challenge is never resubmitted", async () => {
    const user = userEvent.setup();
    const verifyMutateAsync = vi.fn().mockRejectedValue(httpError(401, "MFA_INVALID"));
    mockedUseMfaVerify.mockReturnValue({ mutateAsync: verifyMutateAsync } as never);
    await reachMfaStep(user);

    await user.type(screen.getByLabelText(/verification code/i), "000000");
    await user.click(screen.getByRole("button", { name: /verify/i }));

    await screen.findByLabelText(/email/i);
    expect(screen.queryByLabelText(/verification code/i)).toBeNull();
    expect(verifyMutateAsync).toHaveBeenCalledTimes(1);
  });

  it("on RESOURCE_EXPIRED, shows a safe message and returns to the login form", async () => {
    const user = userEvent.setup();
    const verifyMutateAsync = vi.fn().mockRejectedValue(httpError(410, "RESOURCE_EXPIRED"));
    mockedUseMfaVerify.mockReturnValue({ mutateAsync: verifyMutateAsync } as never);
    await reachMfaStep(user);

    await user.type(screen.getByLabelText(/verification code/i), "000000");
    await user.click(screen.getByRole("button", { name: /verify/i }));

    await screen.findByLabelText(/email/i);
    expect(screen.queryByLabelText(/verification code/i)).toBeNull();
  });

  it("never renders challenge_id anywhere on the verify step itself", async () => {
    const user = userEvent.setup();
    await reachMfaStep(user);

    expect(screen.queryByText(/secret-challenge-id/)).toBeNull();
    expect(document.body.innerHTML).not.toContain("secret-challenge-id");
  });
});
