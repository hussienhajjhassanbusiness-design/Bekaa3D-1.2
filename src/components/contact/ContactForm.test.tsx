import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ContactForm } from "./ContactForm";

// FVS-016-IMPLEMENTATION-PLAN.md T02 — only the three VS-015-confirmed
// fields exist (name, email, message) — no phone/subject/company was
// invented. Reuses the shared guest-submission copy
// (GUEST_SUBMISSION_ERROR_COPY) so Contact and BYI never drift into two
// slightly different vocabularies for the same captcha/rate-limit UX.

describe("ContactForm", () => {
  it("renders an accessible name field", () => {
    render(<ContactForm onSubmit={vi.fn()} />);
    expect(screen.getByLabelText(/name/i).tagName).toBe("INPUT");
  });

  it("renders an accessible email field using native email semantics", () => {
    render(<ContactForm onSubmit={vi.fn()} />);
    expect(screen.getByLabelText(/email/i)).toHaveAttribute("type", "email");
  });

  it("renders an accessible message field", () => {
    render(<ContactForm onSubmit={vi.fn()} />);
    expect(screen.getByLabelText(/message/i).tagName).toBe("TEXTAREA");
  });

  it("renders no unconfirmed fields (phone/subject/company)", () => {
    render(<ContactForm onSubmit={vi.fn()} />);
    expect(screen.queryByLabelText(/phone/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/subject/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/company/i)).not.toBeInTheDocument();
  });

  it("calls onSubmit with the normalized form values", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<ContactForm onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText(/name/i), "Ada Lovelace");
    await user.type(screen.getByLabelText(/email/i), "ada@example.com");
    await user.type(screen.getByLabelText(/message/i), "Interested in a custom stand.");
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(onSubmit).toHaveBeenCalledWith({
      name: "Ada Lovelace",
      email: "ada@example.com",
      message: "Interested in a custom stand.",
    });
  });

  it("disables the submit button while isSubmitting, preventing a duplicate submit", () => {
    render(<ContactForm onSubmit={vi.fn()} isSubmitting />);
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  });

  it("shows the shared captcha guidance for a captcha error", () => {
    render(<ContactForm onSubmit={vi.fn()} error={{ kind: "captcha", message: "irrelevant" }} />);
    expect(screen.getByText("Please complete the verification and try again.")).toBeInTheDocument();
  });

  it("shows the shared rate-limit guidance for a rate-limit error", () => {
    render(<ContactForm onSubmit={vi.fn()} error={{ kind: "rate-limit", message: "irrelevant" }} />);
    expect(screen.getByText("Please try again in a few minutes.")).toBeInTheDocument();
  });

  it("shows the shared generic guidance for a generic error, never the raw message", () => {
    render(<ContactForm onSubmit={vi.fn()} error={{ kind: "generic", message: "raw internal detail" }} />);
    expect(screen.getByText("Something went wrong. Please try again.")).toBeInTheDocument();
    expect(screen.queryByText("raw internal detail")).not.toBeInTheDocument();
  });

  it("renders a supplied captcha slot without building a fake captcha itself", () => {
    render(<ContactForm onSubmit={vi.fn()} captchaSlot={<div data-testid="captcha-slot">real widget here</div>} />);
    expect(screen.getByTestId("captcha-slot")).toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<ContactForm onSubmit={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", async () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    const user = userEvent.setup();
    render(<ContactForm onSubmit={vi.fn()} />);
    await user.type(screen.getByLabelText(/name/i), "a");
    expect(spy).not.toHaveBeenCalled();
  });
});
