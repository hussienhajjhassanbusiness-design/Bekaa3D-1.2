import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BringYourIdeaForm } from "./BringYourIdeaForm";

// FVS-015-IMPLEMENTATION-PLAN.md T02/T03 — only the two backend-
// confirmed fields exist (description, attachments) — no name/email/
// phone/address/budget was invented. Attachments reuse the EXISTING
// `precheckFiles` pure helper from FVS-012's uploadTypes.ts rather than
// a second uploader; FVS-012's `FileUploader` component itself is NOT
// reused here, because its per-file immediate-upload-on-selection model
// doesn't match VS-014's confirmed single bundled multipart
// `CustomRequestCreate` request (see plan §0's audit finding) — this
// form only collects File objects locally, with zero upload attempted
// until the (currently blocked) real submission adapter exists.

function makeFile(name: string, type: string, sizeBytes = 10): File {
  return new File([new Uint8Array(sizeBytes)], name, { type });
}

describe("BringYourIdeaForm", () => {
  it("renders an accessible description field", () => {
    render(<BringYourIdeaForm onSubmit={vi.fn()} />);
    expect(screen.getByLabelText(/description/i).tagName).toBe("TEXTAREA");
  });

  it("renders no unconfirmed fields (name/email/phone)", () => {
    render(<BringYourIdeaForm onSubmit={vi.fn()} />);
    expect(screen.queryByLabelText(/name/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/email/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/phone/i)).not.toBeInTheDocument();
  });

  it("calls onSubmit with the description and selected attachments", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<BringYourIdeaForm onSubmit={onSubmit} />);
    const file = makeFile("idea.png", "image/png");

    await user.type(screen.getByLabelText(/description/i), "A custom stand");
    await user.upload(screen.getByLabelText(/attachments/i), file);
    await user.click(screen.getByRole("button", { name: /submit/i }));

    expect(onSubmit).toHaveBeenCalledWith({ description: "A custom stand", attachments: [file] });
  });

  it("disables the submit button while isSubmitting, preventing a duplicate submit", () => {
    render(<BringYourIdeaForm onSubmit={vi.fn()} isSubmitting />);
    expect(screen.getByRole("button", { name: /submit/i })).toBeDisabled();
  });

  it("shows safe generic guidance for a generic error", () => {
    render(<BringYourIdeaForm onSubmit={vi.fn()} error={{ kind: "generic", message: "raw internal detail" }} />);
    expect(screen.getByText("Something went wrong. Please try again.")).toBeInTheDocument();
    expect(screen.queryByText("raw internal detail")).not.toBeInTheDocument();
  });

  it("shows distinct captcha guidance for a captcha error", () => {
    render(<BringYourIdeaForm onSubmit={vi.fn()} error={{ kind: "captcha", message: "irrelevant" }} />);
    expect(screen.getByText("Please complete the verification and try again.")).toBeInTheDocument();
  });

  it("shows distinct rate-limit guidance for a rate-limit error", () => {
    render(<BringYourIdeaForm onSubmit={vi.fn()} error={{ kind: "rate-limit", message: "irrelevant" }} />);
    expect(screen.getByText("Please try again in a few minutes.")).toBeInTheDocument();
  });

  it("shows the backend-confirmed attachment message verbatim", () => {
    render(<BringYourIdeaForm onSubmit={vi.fn()} error={{ kind: "attachment", message: "This file type isn't supported." }} />);
    expect(screen.getByText("This file type isn't supported.")).toBeInTheDocument();
  });

  it("rejects a disallowed attachment locally using the shared precheck logic, never including it in the submission", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(
      <BringYourIdeaForm onSubmit={onSubmit} attachmentConfig={{ allowedMimeTypes: ["image/png"] }} />
    );
    const file = makeFile("notes.txt", "text/plain");

    await user.upload(screen.getByLabelText(/attachments/i), file);

    expect(screen.getByRole("alert")).toHaveTextContent("notes.txt");

    await user.type(screen.getByLabelText(/description/i), "desc");
    await user.click(screen.getByRole("button", { name: /submit/i }));

    expect(onSubmit).toHaveBeenCalledWith({ description: "desc", attachments: [] });
  });

  it("imposes no hardcoded attachment limit when none is configured", async () => {
    const user = userEvent.setup();
    render(<BringYourIdeaForm onSubmit={vi.fn()} />);
    const file = makeFile("anything.xyz", "application/octet-stream", 50_000_000);

    await user.upload(screen.getByLabelText(/attachments/i), file);

    expect(screen.getByText("anything.xyz")).toBeInTheDocument();
  });

  it("announces attachment additions and removals via aria-live", async () => {
    const user = userEvent.setup();
    render(<BringYourIdeaForm onSubmit={vi.fn()} />);
    const file = makeFile("idea.png", "image/png");

    await user.upload(screen.getByLabelText(/attachments/i), file);
    expect(screen.getByRole("status")).toHaveTextContent(/added/i);

    await user.click(screen.getByRole("button", { name: /remove idea\.png/i }));
    expect(screen.getByRole("status")).toHaveTextContent(/removed/i);
  });

  it("lets the guest remove a selected attachment before submitting", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<BringYourIdeaForm onSubmit={onSubmit} />);
    const file = makeFile("idea.png", "image/png");

    await user.upload(screen.getByLabelText(/attachments/i), file);
    await user.click(screen.getByRole("button", { name: /remove idea\.png/i }));
    await user.type(screen.getByLabelText(/description/i), "desc");
    await user.click(screen.getByRole("button", { name: /submit/i }));

    expect(onSubmit).toHaveBeenCalledWith({ description: "desc", attachments: [] });
    expect(screen.queryByText("idea.png")).not.toBeInTheDocument();
  });

  it("renders a supplied captcha slot without building a fake captcha itself", () => {
    render(<BringYourIdeaForm onSubmit={vi.fn()} captchaSlot={<div data-testid="captcha-slot">real widget here</div>} />);
    expect(screen.getByTestId("captcha-slot")).toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<BringYourIdeaForm onSubmit={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", async () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    const user = userEvent.setup();
    render(<BringYourIdeaForm onSubmit={vi.fn()} />);
    await user.upload(screen.getByLabelText(/attachments/i), makeFile("idea.png", "image/png"));
    expect(spy).not.toHaveBeenCalled();
  });
});
