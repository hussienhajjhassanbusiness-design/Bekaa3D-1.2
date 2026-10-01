import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ResendVerification from "./page";
import { useResendVerification } from "@/lib/auth/useResendVerification";

// FVS002-T10 — mocks useResendVerification (the hook, not apiClient/fetch),
// matching the register/verify-email page precedent. The hook's own
// apiClient wiring is proven separately in useResendVerification.test.ts;
// this file tests validation/UX/enumeration-safety/cooldown/accessibility
// behavior given each of that hook's real return shapes. Real timers are
// used (not faked) since userEvent's own internals interact with timers —
// cooldown-timing assertions use generous, deterministic waits instead.

vi.mock("@/lib/auth/useResendVerification", () => ({
  useResendVerification: vi.fn(),
}));

const mockedUseResendVerification = vi.mocked(useResendVerification);

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
  await user.click(screen.getByRole("button", { name: /resend/i }));
}

beforeEach(() => {
  mockedUseResendVerification.mockReset();
});

describe("ResendVerification (/verify-email/resend)", () => {
  it("renders a labeled email field and a resend button", () => {
    mockedUseResendVerification.mockReturnValue({ mutateAsync: vi.fn() } as never);
    render(<ResendVerification />);

    expect(screen.getByRole("heading", { name: /resend verification email/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /resend/i })).toBeInTheDocument();
  });

  it("the primary submit CTA is full-width, per the plan's mobile/desktop full-width-CTA requirement", () => {
    mockedUseResendVerification.mockReturnValue({ mutateAsync: vi.fn() } as never);
    render(<ResendVerification />);

    expect(screen.getByRole("button", { name: /resend/i })).toHaveClass("w-full");
  });

  it("rejects a malformed email client-side without calling the mutation", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn();
    mockedUseResendVerification.mockReturnValue({ mutateAsync } as never);
    render(<ResendVerification />);

    await user.click(screen.getByRole("button", { name: /resend/i }));

    await screen.findByRole("status");
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("submits the exact { email } body on a valid submit, preserving case/content verbatim (not trimmed/rewritten)", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ message: "sent" });
    mockedUseResendVerification.mockReturnValue({ mutateAsync } as never);
    render(<ResendVerification />);

    await submitValidEmail(user, "Ada.Lovelace@Example.com");

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ email: "Ada.Lovelace@Example.com" }));
  });

  it("prevents a rapid double submission from firing the mutation twice", async () => {
    const user = userEvent.setup();
    let resolveMutate!: (value: { message: string }) => void;
    const mutateAsync = vi.fn(() => new Promise((resolve) => { resolveMutate = resolve; }));
    mockedUseResendVerification.mockReturnValue({ mutateAsync } as never);
    render(<ResendVerification />);

    await user.type(screen.getByLabelText(/email/i), "ada@example.com");
    const submitButton = screen.getByRole("button", { name: /resend/i });
    await user.click(submitButton);
    await user.click(submitButton);

    resolveMutate({ message: "sent" });
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
  });

  it("shows identical success copy whether the mocked account exists or not (enumeration safety)", async () => {
    const user = userEvent.setup();

    const mutateAsyncExisting = vi.fn().mockResolvedValue({ message: "we sent it to your existing account" });
    mockedUseResendVerification.mockReturnValue({ mutateAsync: mutateAsyncExisting } as never);
    const { unmount } = render(<ResendVerification />);
    await submitValidEmail(user);
    const existingCopy = (await screen.findByText(/if an account exists/i)).textContent;
    unmount();

    const mutateAsyncMissing = vi.fn().mockResolvedValue({ message: "no account found for this email" });
    mockedUseResendVerification.mockReturnValue({ mutateAsync: mutateAsyncMissing } as never);
    render(<ResendVerification />);
    await submitValidEmail(user);
    const missingCopy = (await screen.findByText(/if an account exists/i)).textContent;

    expect(existingCopy).toBe(missingCopy);
    expect(existingCopy).not.toMatch(/no account found/i);
  });

  it("moves focus to the success message after a successful resend, so it never silently lands on <body>", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ message: "sent" });
    mockedUseResendVerification.mockReturnValue({ mutateAsync } as never);
    render(<ResendVerification />);

    await submitValidEmail(user);

    const successRegion = await screen.findByText(/if an account exists/i);
    await waitFor(() => expect(successRegion.closest('[tabindex="-1"]')).toHaveFocus());
  });

  it("starts a 120-second cooldown and disables the resend button immediately after a successful 202", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ message: "sent" });
    mockedUseResendVerification.mockReturnValue({ mutateAsync } as never);
    render(<ResendVerification />);

    await submitValidEmail(user);

    await screen.findByText(/if an account exists/i);
    expect(screen.getByRole("button", { name: /resend/i })).toBeDisabled();
    expect(screen.getByText(/120/)).toBeInTheDocument();
  });

  it("shows a static 'resend available at HH:MM:SS' announcement once, derived from the absolute deadline", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ message: "sent" });
    mockedUseResendVerification.mockReturnValue({ mutateAsync } as never);
    render(<ResendVerification />);

    await submitValidEmail(user);

    const region = await screen.findByText(/resend available at \d{2}:\d{2}:\d{2}/i);
    expect(region.closest('[aria-live="polite"]')).toBeTruthy();
  });

  it("the visible ticking countdown text is not itself an aria-live region", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ message: "sent" });
    mockedUseResendVerification.mockReturnValue({ mutateAsync } as never);
    render(<ResendVerification />);

    await submitValidEmail(user);

    const ticking = await screen.findByTestId("resend-countdown-ticking");
    expect(ticking.closest('[aria-live]')).toBeNull();
  });

  it("announces the start of the cooldown exactly once in the aria-live region (not once per tick)", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ message: "sent" });
    mockedUseResendVerification.mockReturnValue({ mutateAsync } as never);
    render(<ResendVerification />);

    await submitValidEmail(user);
    await screen.findByText(/resend available at/i);

    const liveRegion = screen.getByTestId("resend-live-region");
    const firstAnnouncement = liveRegion.textContent;

    await new Promise((resolve) => setTimeout(resolve, 1100));

    expect(liveRegion.textContent).toBe(firstAnnouncement);
  });

  it("the start announcement does not already contain the completion message (completion is a distinct, later announcement)", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ message: "sent" });
    mockedUseResendVerification.mockReturnValue({ mutateAsync } as never);
    render(<ResendVerification />);

    await submitValidEmail(user);
    await screen.findByText(/resend available at/i);

    const liveRegion = screen.getByTestId("resend-live-region");
    expect(liveRegion.textContent).not.toMatch(/you can resend.*now/i);
  });

  it("maps a 429 with a Retry-After of 3600 seconds to a 3600-second deadline, not the normal 120-second cooldown", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue(httpError(429, { retryAfterSeconds: 3600 }));
    mockedUseResendVerification.mockReturnValue({ mutateAsync } as never);
    render(<ResendVerification />);

    await submitValidEmail(user);

    await waitFor(() => expect(screen.getAllByText(/1 hour/i).length).toBeGreaterThan(0));
    expect(screen.getByRole("button", { name: /resend/i })).toBeDisabled();
  });

  it("does not re-announce the rate-limit Alert every tick for a short (<60s) Retry-After — the live warning Alert's text must stay stable while only the non-live ticking paragraph changes", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue(httpError(429, { retryAfterSeconds: 30 }));
    mockedUseResendVerification.mockReturnValue({ mutateAsync } as never);
    render(<ResendVerification />);

    await submitValidEmail(user);

    // The warning Alert (role="status", aria-live="polite" per Alert.tsx)
    // must never change its text once rendered — only the separate,
    // non-live ticking paragraph may update every second.
    const alertBefore = await screen.findByText(/too many attempts/i);
    const textBefore = alertBefore.textContent;

    await new Promise((resolve) => setTimeout(resolve, 2100));

    const alertAfter = screen.getByText(/too many attempts/i);
    expect(alertAfter.textContent).toBe(textBefore);
  });

  it("shows a safe rate-limit failure without inventing a duration when Retry-After is missing", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue(httpError(429));
    mockedUseResendVerification.mockReturnValue({ mutateAsync } as never);
    render(<ResendVerification />);

    await submitValidEmail(user);

    const alert = await screen.findByText(/too many/i);
    expect(alert).toBeInTheDocument();
    expect(screen.queryByTestId("resend-countdown-ticking")).toBeNull();
  });

  it("shows a safe alert on a network failure", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue(networkError());
    mockedUseResendVerification.mockReturnValue({ mutateAsync } as never);
    render(<ResendVerification />);

    await submitValidEmail(user);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/couldn't reach|try again/i);
  });

  it("shows a safe alert on a timeout failure", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue(timeoutError());
    mockedUseResendVerification.mockReturnValue({ mutateAsync } as never);
    render(<ResendVerification />);

    await submitValidEmail(user);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/took too long|try again/i);
  });

  it("shows a safe generic alert on an unrecognized HTTP failure, never rendering ApiError.raw", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue({
      kind: "http",
      status: 500,
      message: "Something went wrong. Please try again.",
      raw: { title: "SECRET_RAW_DIAGNOSTIC_TEXT" },
    });
    mockedUseResendVerification.mockReturnValue({ mutateAsync } as never);
    render(<ResendVerification />);

    await submitValidEmail(user);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/something went wrong|try again/i);
    expect(screen.queryByText(/SECRET_RAW_DIAGNOSTIC_TEXT/)).toBeNull();
  });

  it("never branches copy or behavior on account existence anywhere in the component", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ message: "existing" });
    mockedUseResendVerification.mockReturnValue({ mutateAsync } as never);
    render(<ResendVerification />);

    await submitValidEmail(user);

    await screen.findByText(/if an account exists/i);
    expect(screen.queryByText(/not found|not registered|already sent for this user|^email exists$/i)).toBeNull();
  });
});
