import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import VerifyEmail from "./page";
import { useVerifyEmail } from "@/lib/auth/useVerifyEmail";

// FVS002-T09 — mocks useVerifyEmail (the hook, not apiClient/fetch), matching
// the precedent established for the register page (mock the owning hook for
// a page-level test; the hook's own apiClient wiring is proven separately in
// useVerifyEmail.test.ts).
vi.mock("@/lib/auth/useVerifyEmail", () => ({
  useVerifyEmail: vi.fn(),
}));

const mockedUseVerifyEmail = vi.mocked(useVerifyEmail);
const VALID_TOKEN = "a".repeat(43);

function httpError(status: number, extra: Record<string, unknown> = {}) {
  return { kind: "http" as const, status, message: "Something went wrong. Please try again.", raw: { status }, ...extra };
}

function networkError() {
  return { kind: "network" as const, message: "We couldn't reach the server.", raw: undefined };
}

function timeoutError() {
  return { kind: "timeout" as const, message: "The server took too long to respond. Please try again.", raw: undefined };
}

function setHash(hash: string) {
  window.location.hash = hash;
}

beforeEach(() => {
  mockedUseVerifyEmail.mockReset();
});

afterEach(() => {
  window.location.hash = "";
});

describe("VerifyEmail (/verify-email)", () => {
  it("sends exactly one POST with the exact path and body for a valid token", async () => {
    setHash(`#token=${VALID_TOKEN}`);
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockedUseVerifyEmail.mockReturnValue({ mutateAsync } as never);

    render(<VerifyEmail />);

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    expect(mutateAsync).toHaveBeenCalledWith({ token: VALID_TOKEN });
  });

  it("shows a loading state before the mutation settles", () => {
    setHash(`#token=${VALID_TOKEN}`);
    const mutateAsync = vi.fn(() => new Promise(() => {}));
    mockedUseVerifyEmail.mockReturnValue({ mutateAsync } as never);

    render(<VerifyEmail />);

    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("shows a success state with a /login link on 204 (undefined resolution)", async () => {
    setHash(`#token=${VALID_TOKEN}`);
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockedUseVerifyEmail.mockReturnValue({ mutateAsync } as never);

    render(<VerifyEmail />);

    expect(await screen.findByText(/verified/i)).toBeInTheDocument();
    const loginLink = screen.getByRole("link", { name: /log in/i });
    expect(loginLink).toHaveAttribute("href", "/login");
  });

  it("shows the invalid state and makes no request when the hash is missing", () => {
    const mutateAsync = vi.fn();
    mockedUseVerifyEmail.mockReturnValue({ mutateAsync } as never);

    render(<VerifyEmail />);

    expect(mutateAsync).not.toHaveBeenCalled();
    expect(screen.getByText(/isn't valid|not valid/i)).toBeInTheDocument();
  });

  it("shows the invalid state and makes no request when the token key is missing from the fragment", () => {
    setHash("#foo=bar");
    const mutateAsync = vi.fn();
    mockedUseVerifyEmail.mockReturnValue({ mutateAsync } as never);

    render(<VerifyEmail />);

    expect(mutateAsync).not.toHaveBeenCalled();
    expect(screen.getByText(/isn't valid|not valid/i)).toBeInTheDocument();
  });

  it("shows the invalid state and makes no request for an empty token value", () => {
    setHash("#token=");
    const mutateAsync = vi.fn();
    mockedUseVerifyEmail.mockReturnValue({ mutateAsync } as never);

    render(<VerifyEmail />);

    expect(mutateAsync).not.toHaveBeenCalled();
    expect(screen.getByText(/isn't valid|not valid/i)).toBeInTheDocument();
  });

  it("shows the invalid state and makes no request for a token that is not exactly 43 characters", () => {
    setHash("#token=tooshort");
    const mutateAsync = vi.fn();
    mockedUseVerifyEmail.mockReturnValue({ mutateAsync } as never);

    render(<VerifyEmail />);

    expect(mutateAsync).not.toHaveBeenCalled();
    expect(screen.getByText(/isn't valid|not valid/i)).toBeInTheDocument();
  });

  it("parses a percent-encoded fragment safely without throwing", () => {
    setHash(`#token=${encodeURIComponent(VALID_TOKEN)}&next=%2Fsomewhere`);
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockedUseVerifyEmail.mockReturnValue({ mutateAsync } as never);

    expect(() => render(<VerifyEmail />)).not.toThrow();
    expect(mutateAsync).toHaveBeenCalledWith({ token: VALID_TOKEN });
  });

  it("maps a 400 INVALID_TOKEN response to the generic invalid state with a resend link", async () => {
    setHash(`#token=${VALID_TOKEN}`);
    const mutateAsync = vi.fn().mockRejectedValue(httpError(400));
    mockedUseVerifyEmail.mockReturnValue({ mutateAsync } as never);

    render(<VerifyEmail />);

    expect(await screen.findByText(/isn't valid|not valid/i)).toBeInTheDocument();
    const resendLink = screen.getByRole("link", { name: /resend|new link|request/i });
    expect(resendLink).toHaveAttribute("href", "/verify-email/resend");
  });

  it("maps a 410 RESOURCE_EXPIRED response to a distinct expired state", async () => {
    setHash(`#token=${VALID_TOKEN}`);
    const mutateAsync = vi.fn().mockRejectedValue(httpError(410));
    mockedUseVerifyEmail.mockReturnValue({ mutateAsync } as never);

    render(<VerifyEmail />);

    expect(await screen.findByText(/expired/i)).toBeInTheDocument();
  });

  it("expired copy communicates both 'log in if already verified' and 'request a new link'", async () => {
    setHash(`#token=${VALID_TOKEN}`);
    const mutateAsync = vi.fn().mockRejectedValue(httpError(410));
    mockedUseVerifyEmail.mockReturnValue({ mutateAsync } as never);

    render(<VerifyEmail />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/log in/i);
    expect(alert).toHaveTextContent(/new link|resend/i);
  });

  it("the expired state links to both /login and /verify-email/resend", async () => {
    setHash(`#token=${VALID_TOKEN}`);
    const mutateAsync = vi.fn().mockRejectedValue(httpError(410));
    mockedUseVerifyEmail.mockReturnValue({ mutateAsync } as never);

    render(<VerifyEmail />);

    await screen.findByRole("alert");
    expect(screen.getByRole("link", { name: /log in/i })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: /resend|new link|request/i })).toHaveAttribute(
      "href",
      "/verify-email/resend"
    );
  });

  it("maps a 429 response to a safe rate-limit state", async () => {
    setHash(`#token=${VALID_TOKEN}`);
    const mutateAsync = vi.fn().mockRejectedValue(httpError(429, { retryAfterSeconds: 60 }));
    mockedUseVerifyEmail.mockReturnValue({ mutateAsync } as never);

    render(<VerifyEmail />);

    expect(await screen.findByText(/too many|wait/i)).toBeInTheDocument();
  });

  it("maps a network failure to a safe unavailable state", async () => {
    setHash(`#token=${VALID_TOKEN}`);
    const mutateAsync = vi.fn().mockRejectedValue(networkError());
    mockedUseVerifyEmail.mockReturnValue({ mutateAsync } as never);

    render(<VerifyEmail />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/couldn't reach|try again/i);
  });

  it("maps a timeout failure to a safe unavailable state", async () => {
    setHash(`#token=${VALID_TOKEN}`);
    const mutateAsync = vi.fn().mockRejectedValue(timeoutError());
    mockedUseVerifyEmail.mockReturnValue({ mutateAsync } as never);

    render(<VerifyEmail />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/took too long|try again/i);
  });

  it("maps an unrecognized HTTP failure (e.g. 500) to a safe generic failure state", async () => {
    setHash(`#token=${VALID_TOKEN}`);
    const mutateAsync = vi.fn().mockRejectedValue(httpError(500));
    mockedUseVerifyEmail.mockReturnValue({ mutateAsync } as never);

    render(<VerifyEmail />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/something went wrong|try again/i);
  });

  it("never renders the token value anywhere on the page", async () => {
    setHash(`#token=${VALID_TOKEN}`);
    const mutateAsync = vi.fn().mockRejectedValue(httpError(400));
    mockedUseVerifyEmail.mockReturnValue({ mutateAsync } as never);

    render(<VerifyEmail />);

    await screen.findByRole("alert");
    expect(screen.queryByText(VALID_TOKEN)).toBeNull();
  });

  it("never renders raw diagnostic content from ApiError.raw", async () => {
    setHash(`#token=${VALID_TOKEN}`);
    const mutateAsync = vi.fn().mockRejectedValue({
      kind: "http",
      status: 400,
      message: "Something went wrong. Please try again.",
      raw: { type: "https://example.com/probs/invalid-token", title: "SECRET_RAW_DIAGNOSTIC_TEXT" },
    });
    mockedUseVerifyEmail.mockReturnValue({ mutateAsync } as never);

    render(<VerifyEmail />);

    await screen.findByRole("alert");
    expect(screen.queryByText(/SECRET_RAW_DIAGNOSTIC_TEXT/)).toBeNull();
  });

  it("fires exactly one POST even under React Strict Mode's dev-only double-invoke of effects", async () => {
    setHash(`#token=${VALID_TOKEN}`);
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockedUseVerifyEmail.mockReturnValue({ mutateAsync } as never);

    render(
      <StrictMode>
        <VerifyEmail />
      </StrictMode>
    );

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
  });
});
