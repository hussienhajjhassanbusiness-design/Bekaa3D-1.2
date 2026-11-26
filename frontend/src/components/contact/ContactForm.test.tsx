import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ContactForm } from "./ContactForm";
import { useSubmitContactMessage } from "@/lib/contact/contactApi";
import { CAPTCHA_FAILURE_COPY } from "@/lib/captcha/captchaErrors";
import { FAKE_CAPTCHA_TOKEN, fakeCaptcha, resetFakeCaptcha } from "@/test/fakeCaptchaWidget";

vi.mock("@/lib/contact/contactApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/contact/contactApi")>();
  return { ...actual, useSubmitContactMessage: vi.fn() };
});

vi.mock("@/components/forms/CaptchaWidget", async () => {
  const fake = await import("@/test/fakeCaptchaWidget");
  return { CaptchaWidget: fake.FakeCaptchaWidget };
});

const mocked = vi.mocked(useSubmitContactMessage);

async function fillRequired(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Name"), "Rana");
  await user.type(screen.getByLabelText("Email"), "rana@example.com");
  await user.type(screen.getByLabelText("Message"), "Do you print in PETG?");
}

beforeEach(() => {
  mocked.mockReset();
  resetFakeCaptcha();
});

describe("ContactForm", () => {
  it("renders labelled backend fields only", () => {
    mocked.mockReturnValue({ mutateAsync: vi.fn() } as never);
    render(<ContactForm />);
    for (const label of ["Name", "Email", "Phone (optional)", "Subject (optional)", "Message"]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    }
  });

  it("blocks an empty or malformed submit client-side", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn();
    mocked.mockReturnValue({ mutateAsync } as never);
    render(<ContactForm />);
    await user.type(screen.getByLabelText("Phone (optional)"), "call me");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(await screen.findByText("Enter your name.", { selector: "p" })).toBeInTheDocument();
    expect(screen.getByText("Enter a valid phone number.", { selector: "p" })).toBeInTheDocument();
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("sends the exact payload, then shows a safe success state", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ id: "secret-id", created_at: "2026-11-11T10:00:00Z" });
    mocked.mockReturnValue({ mutateAsync } as never);
    render(<ContactForm />);
    await fillRequired(user);
    await user.type(screen.getByLabelText("Subject (optional)"), "Materials");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({
        name: "Rana",
        email: "rana@example.com",
        subject: "Materials",
        message: "Do you print in PETG?",
        captcha_token: FAKE_CAPTCHA_TOKEN,
      })
    );
    expect(await screen.findByText(/your message has been sent/i)).toBeInTheDocument();
    expect(screen.queryByText(/secret-id/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Send another message" }));
    expect(screen.getByLabelText("Name")).toHaveValue("");
  });

  it("shows captcha copy on CAPTCHA_INVALID and retries with a fresh token", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi
      .fn()
      .mockRejectedValueOnce({ kind: "http", status: 400, code: "CAPTCHA_INVALID", detail: "RAW", message: "x", raw: {} })
      .mockResolvedValueOnce({ id: "m", created_at: "x" });
    mocked.mockReturnValue({ mutateAsync } as never);
    render(<ContactForm />);
    await fillRequired(user);
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(CAPTCHA_FAILURE_COPY.invalid);
    expect(screen.queryByText("RAW")).not.toBeInTheDocument();
    expect(fakeCaptcha.resetCount).toBe(1);
    await user.click(screen.getByRole("button", { name: "Send message" }));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/your message has been sent/i)).toBeInTheDocument();
  });

  it("refuses to submit without a captcha token", async () => {
    fakeCaptcha.autoIssue = false;
    const user = userEvent.setup();
    const mutateAsync = vi.fn();
    mocked.mockReturnValue({ mutateAsync } as never);
    render(<ContactForm />);
    await fillRequired(user);
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(CAPTCHA_FAILURE_COPY.missing);
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("shows rate-limit and field copy, never the server's text", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi
      .fn()
      .mockRejectedValueOnce({ kind: "http", status: 429, code: "RATE_LIMITED", retryAfterSeconds: 600, detail: "RAW", message: "x", raw: {} })
      .mockRejectedValueOnce({
        kind: "http",
        status: 422,
        code: "VALIDATION_ERROR",
        errors: [{ loc: ["body", "email"], msg: "RAW MSG", type: "value_error" }],
        message: "x",
        raw: {},
      });
    mocked.mockReturnValue({ mutateAsync } as never);
    render(<ContactForm />);
    await fillRequired(user);
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Please try again in about 10 minutes.");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Please check: Email."));
    expect(screen.queryByText(/RAW/)).not.toBeInTheDocument();
  });
});
