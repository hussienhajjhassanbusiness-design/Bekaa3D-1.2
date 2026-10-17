import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ForgotPassword from "./page";
import { usePasswordResetRequest } from "@/lib/auth/usePasswordResetRequest";

// Phase 2 auth/account batch — mounts FVS-004's request half. Mocks the
// hook (not apiClient/fetch), matching the register/resend-verification
// page precedent; the hook's own apiClient wiring is proven separately in
// usePasswordResetRequest.test.ts.

vi.mock("@/lib/auth/usePasswordResetRequest", () => ({
  usePasswordResetRequest: vi.fn(),
}));

const mockedUsePasswordResetRequest = vi.mocked(usePasswordResetRequest);

function httpError(status: number, extra: Record<string, unknown> = {}) {
  return { kind: "http" as const, status, message: "Something went wrong. Please try again.", raw: { status }, ...extra };
}

function networkError() {
  return { kind: "network" as const, message: "We couldn't reach the server.", raw: undefined };
}

function timeoutError() {
  return { kind: "timeout" as const, message: "The server took too long to respond. Please try again.", raw: undefined };
}

async function submitValidEmail(user: ReturnType<typeof userEvent.setup>, email = "ada@example.com") {
  await user.type(screen.getByLabelText(/email/i), email);
  await user.click(screen.getByRole("button", { name: /send reset link/i }));
}

beforeEach(() => {
  mockedUsePasswordResetRequest.mockReset();
});

describe("ForgotPassword (/forgot-password)", () => {
  it("renders a labeled email field and a submit button", () => {
    mockedUsePasswordResetRequest.mockReturnValue({ mutateAsync: vi.fn() } as never);
    render(<ForgotPassword />);

    expect(screen.getByRole("heading", { name: /reset your password/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /send reset link/i })).toBeInTheDocument();
  });

  it("rejects a malformed email client-side without calling the mutation", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn();
    mockedUsePasswordResetRequest.mockReturnValue({ mutateAsync } as never);
    render(<ForgotPassword />);

    await user.click(screen.getByRole("button", { name: /send reset link/i }));

    await screen.findByRole("status");
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("submits the exact { email } body on a valid submit", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ message: "sent" });
    mockedUsePasswordResetRequest.mockReturnValue({ mutateAsync } as never);
    render(<ForgotPassword />);

    await submitValidEmail(user, "Ada.Lovelace@Example.com");

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ email: "Ada.Lovelace@Example.com" }));
  });

  it("shows identical success copy whether the mocked account exists or not (enumeration safety)", async () => {
    const user = userEvent.setup();

    const mutateAsyncExisting = vi.fn().mockResolvedValue({ message: "we sent it to your existing account" });
    mockedUsePasswordResetRequest.mockReturnValue({ mutateAsync: mutateAsyncExisting } as never);
    const { unmount } = render(<ForgotPassword />);
    await submitValidEmail(user);
    const existingCopy = (await screen.findByText(/if an account exists/i)).textContent;
    unmount();

    const mutateAsyncMissing = vi.fn().mockResolvedValue({ message: "no account found for this email" });
    mockedUsePasswordResetRequest.mockReturnValue({ mutateAsync: mutateAsyncMissing } as never);
    render(<ForgotPassword />);
    await submitValidEmail(user);
    const missingCopy = (await screen.findByText(/if an account exists/i)).textContent;

    expect(existingCopy).toBe(missingCopy);
    expect(existingCopy).not.toMatch(/no account found/i);
  });

  it("moves focus to the success heading after a successful submission", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ message: "sent" });
    mockedUsePasswordResetRequest.mockReturnValue({ mutateAsync } as never);
    render(<ForgotPassword />);

    await submitValidEmail(user);

    await screen.findByText(/if an account exists/i);
    await waitFor(() => expect(screen.getByRole("heading", { name: /reset your password/i })).toHaveFocus());
  });

  it("shows a safe alert on a network failure, and keeps the form visible for retry", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue(networkError());
    mockedUsePasswordResetRequest.mockReturnValue({ mutateAsync } as never);
    render(<ForgotPassword />);

    await submitValidEmail(user);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/couldn't reach|try again/i);
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
  });

  it("shows a safe alert on a timeout failure", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue(timeoutError());
    mockedUsePasswordResetRequest.mockReturnValue({ mutateAsync } as never);
    render(<ForgotPassword />);

    await submitValidEmail(user);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/took too long|try again/i);
  });

  it("shows a rate-limit-specific message on 429, without inventing an exact wait when Retry-After is missing", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue(httpError(429));
    mockedUsePasswordResetRequest.mockReturnValue({ mutateAsync } as never);
    render(<ForgotPassword />);

    await submitValidEmail(user);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/too many/i);
  });

  it("shows a safe generic alert on an unrecognized HTTP failure, never rendering ApiError.raw", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue({
      kind: "http",
      status: 500,
      message: "Something went wrong. Please try again.",
      raw: { title: "SECRET_RAW_DIAGNOSTIC_TEXT" },
    });
    mockedUsePasswordResetRequest.mockReturnValue({ mutateAsync } as never);
    render(<ForgotPassword />);

    await submitValidEmail(user);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/something went wrong|try again/i);
    expect(screen.queryByText(/SECRET_RAW_DIAGNOSTIC_TEXT/)).toBeNull();
  });

  it("links to /login", () => {
    mockedUsePasswordResetRequest.mockReturnValue({ mutateAsync: vi.fn() } as never);
    render(<ForgotPassword />);

    expect(screen.getByRole("link", { name: /log in/i })).toHaveAttribute("href", "/login");
  });
});
