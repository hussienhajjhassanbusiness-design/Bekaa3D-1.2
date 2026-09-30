import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Register from "./page";
import { useRegister } from "@/lib/auth/useRegister";

// FVS002-T08 — mocks useRegister (the hook, not apiClient/fetch), matching
// BackendUnreachableBanner.test.tsx's own precedent of mocking the owning
// hook for a page/component-level test. useRegister's own apiClient wiring
// is already proven by useRegister.test.ts; this file tests the page's
// validation/UX/enumeration-safety/error-handling behavior given each of
// that hook's real return shapes.
vi.mock("@/lib/auth/useRegister", () => ({
  useRegister: vi.fn(),
}));

const mockedUseRegister = vi.mocked(useRegister);

function networkError() {
  return { kind: "network" as const, message: "We couldn't reach the server.", raw: undefined };
}

function httpError(status: number) {
  return { kind: "http" as const, status, message: "Something went wrong. Please try again.", raw: { status } };
}

async function fillValidForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/email/i), "ada@example.com");
  await user.type(screen.getByLabelText(/password/i), "correct-horse-battery");
}

beforeEach(() => {
  mockedUseRegister.mockReset();
});

describe("Register (/register)", () => {
  it("renders labeled email and password fields and a submit button", () => {
    mockedUseRegister.mockReturnValue({ mutateAsync: vi.fn() } as never);
    render(<Register />);

    expect(screen.getByRole("heading", { name: /create your account/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create account/i })).toBeInTheDocument();
  });

  it("submits the exact { email, password } body on a valid submit, preserving email case/content verbatim", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ message: "check your email" });
    mockedUseRegister.mockReturnValue({ mutateAsync } as never);
    render(<Register />);

    await user.type(screen.getByLabelText(/email/i), "Ada.Lovelace@Example.com");
    await user.type(screen.getByLabelText(/password/i), "correct-horse-battery");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({
      email: "Ada.Lovelace@Example.com",
      password: "correct-horse-battery",
    }));
  });

  it("does not trim surrounding whitespace from the password before submitting", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ message: "check your email" });
    mockedUseRegister.mockReturnValue({ mutateAsync } as never);
    render(<Register />);

    await user.type(screen.getByLabelText(/email/i), "ada@example.com");
    await user.click(screen.getByLabelText(/password/i));
    await user.paste(" correct horse battery ");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({
      email: "ada@example.com",
      password: " correct horse battery ",
    }));
  });

  it("rejects an empty/malformed email client-side without calling the mutation", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn();
    mockedUseRegister.mockReturnValue({ mutateAsync } as never);
    render(<Register />);

    await user.type(screen.getByLabelText(/password/i), "correct-horse-battery");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await screen.findByRole("status");
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("rejects a password shorter than 8 Unicode code points without calling the mutation", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn();
    mockedUseRegister.mockReturnValue({ mutateAsync } as never);
    render(<Register />);

    await user.type(screen.getByLabelText(/email/i), "ada@example.com");
    await user.type(screen.getByLabelText(/password/i), "short1");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await screen.findByRole("status");
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("rejects a password longer than 256 Unicode code points without calling the mutation", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn();
    mockedUseRegister.mockReturnValue({ mutateAsync } as never);
    render(<Register />);

    await user.type(screen.getByLabelText(/email/i), "ada@example.com");
    await user.type(screen.getByLabelText(/password/i), "a".repeat(257));
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await screen.findByRole("status");
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("counts password length by Unicode code points, not UTF-16 code units — accepts 8 astral-plane characters as long enough", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ message: "check your email" });
    mockedUseRegister.mockReturnValue({ mutateAsync } as never);
    render(<Register />);

    const eightSurrogatePairCharacters = "\u{1F600}".repeat(8); // 8 code points, 16 UTF-16 code units
    await user.type(screen.getByLabelText(/email/i), "ada@example.com");
    await user.click(screen.getByLabelText(/password/i));
    await user.paste(eightSurrogatePairCharacters);
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({
      email: "ada@example.com",
      password: eightSurrogatePairCharacters,
    }));
  });

  it("rejects a password containing a control character without calling the mutation", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn();
    mockedUseRegister.mockReturnValue({ mutateAsync } as never);
    render(<Register />);

    await user.type(screen.getByLabelText(/email/i), "ada@example.com");
    await user.click(screen.getByLabelText(/password/i));
    const bellControlCharacter = String.fromCharCode(7); // BEL (0x07), a C0 control character
    await user.paste(`password1${bellControlCharacter}`);
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await screen.findByRole("status");
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("enforces no complexity rule — an all-lowercase, no-digit password of sufficient length is accepted", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ message: "check your email" });
    mockedUseRegister.mockReturnValue({ mutateAsync } as never);
    render(<Register />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
  });

  it("shows the enumeration-safe success state after a successful submit", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ message: "check your email" });
    mockedUseRegister.mockReturnValue({ mutateAsync } as never);
    render(<Register />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText(/check your email/i)).toBeInTheDocument();
  });

  it("renders identical success copy whether the backend implies a new or an existing account (enumeration safety)", async () => {
    const user = userEvent.setup();

    const mutateAsyncNew = vi.fn().mockResolvedValue({ message: "a brand new account was created" });
    mockedUseRegister.mockReturnValue({ mutateAsync: mutateAsyncNew } as never);
    const { unmount } = render(<Register />);
    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /create account/i }));
    const newAccountCopy = (await screen.findByText(/check your email/i)).textContent;
    unmount();

    const mutateAsyncExisting = vi.fn().mockResolvedValue({ message: "this email is already registered" });
    mockedUseRegister.mockReturnValue({ mutateAsync: mutateAsyncExisting } as never);
    render(<Register />);
    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /create account/i }));
    const existingAccountCopy = (await screen.findByText(/check your email/i)).textContent;

    expect(newAccountCopy).toBe(existingAccountCopy);
    expect(newAccountCopy).not.toMatch(/already registered/i);
  });

  it("shows a safe generic alert on a network failure, never a raw diagnostic", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue(networkError());
    mockedUseRegister.mockReturnValue({ mutateAsync } as never);
    render(<Register />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /create account/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/something went wrong|try again/i);
  });

  it("shows a safe generic alert on an HTTP/server failure, never ApiError.raw", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue(httpError(400));
    mockedUseRegister.mockReturnValue({ mutateAsync } as never);
    render(<Register />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /create account/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/something went wrong|try again/i);
  });

  it("shows a safe rate-limit alert on a 429, without fabricating a countdown", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue(httpError(429));
    mockedUseRegister.mockReturnValue({ mutateAsync } as never);
    render(<Register />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /create account/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/too many|try again/i);
  });

  it("prevents a rapid double submission from firing the mutation twice", async () => {
    const user = userEvent.setup();
    let resolveMutate!: (value: { message: string }) => void;
    const mutateAsync = vi.fn(
      () =>
        new Promise((resolve) => {
          resolveMutate = resolve;
        })
    );
    mockedUseRegister.mockReturnValue({ mutateAsync } as never);
    render(<Register />);

    await fillValidForm(user);
    const submitButton = screen.getByRole("button", { name: /create account/i });
    await user.click(submitButton);
    await user.click(submitButton);

    resolveMutate({ message: "check your email" });
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
  });

  it("never renders ApiError.raw content anywhere on a failure", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockRejectedValue({
      kind: "http",
      status: 400,
      message: "Something went wrong. Please try again.",
      raw: { type: "https://example.com/probs/validation", title: "SECRET_RAW_DIAGNOSTIC_TEXT" },
    });
    mockedUseRegister.mockReturnValue({ mutateAsync } as never);
    render(<Register />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await screen.findByRole("alert");
    expect(screen.queryByText(/SECRET_RAW_DIAGNOSTIC_TEXT/)).toBeNull();
  });
});
