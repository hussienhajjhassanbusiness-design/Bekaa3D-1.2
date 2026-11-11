import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BringYourIdeaForm } from "./BringYourIdeaForm";
import { useSubmitCustomRequest } from "@/lib/byi/customRequestApi";
import { CAPTCHA_FAILURE_COPY } from "@/lib/captcha/captchaErrors";
import { FAKE_CAPTCHA_TOKEN, fakeCaptcha, resetFakeCaptcha } from "@/test/fakeCaptchaWidget";

vi.mock("@/lib/byi/customRequestApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/byi/customRequestApi")>();
  return { ...actual, useSubmitCustomRequest: vi.fn() };
});

vi.mock("@/components/forms/CaptchaWidget", async () => {
  const fake = await import("@/test/fakeCaptchaWidget");
  return { CaptchaWidget: fake.FakeCaptchaWidget };
});

const mocked = vi.mocked(useSubmitCustomRequest);
const png = (name: string, size = 4) => new File([new Uint8Array(size)], name, { type: "image/png" });

async function fillRequired(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Name"), "Rana");
  await user.type(screen.getByLabelText("Email"), "rana@example.com");
  await user.type(screen.getByLabelText("Phone"), "+961 70 123 456");
  await user.type(screen.getByLabelText("Project title"), "Cedar lamp");
  await user.type(screen.getByLabelText("Description"), "A lamp shaped like a cedar.");
}

beforeEach(() => {
  mocked.mockReset();
  resetFakeCaptcha();
});

describe("BringYourIdeaForm", () => {
  it("renders exactly the backend fields and an image-only uploader", () => {
    mocked.mockReturnValue({ mutateAsync: vi.fn() } as never);
    render(<BringYourIdeaForm />);
    for (const label of [
      "Name",
      "Email",
      "Phone",
      "Project title",
      "Description",
      "Preferred material (optional)",
      "Preferred colour (optional)",
      "Dimensions (optional)",
      "Reference images (optional)",
    ]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    }
    expect(screen.getByLabelText("Reference images (optional)")).toHaveAttribute("accept", "image/jpeg,image/png,image/webp");
    expect(screen.queryByLabelText(/budget|deadline|quantity|stl/i)).not.toBeInTheDocument();
  });

  it("requires name, email, phone, title and description client-side", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn();
    mocked.mockReturnValue({ mutateAsync } as never);
    render(<BringYourIdeaForm />);
    await user.click(screen.getByRole("button", { name: "Send my idea" }));
    for (const text of ["Enter your name.", "Enter a phone number.", "Give your project a title.", "Describe your idea."]) {
      expect(await screen.findByText(text, { selector: "p" })).toBeInTheDocument();
    }
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("pre-checks images locally: wrong type, too large, more than five", async () => {
    const user = userEvent.setup({ applyAccept: false });
    mocked.mockReturnValue({ mutateAsync: vi.fn() } as never);
    render(<BringYourIdeaForm />);
    const input = screen.getByLabelText("Reference images (optional)");
    await user.upload(input, new File(["solid"], "model.stl", { type: "model/stl" }));
    expect(await screen.findByText(/"model.stl" isn't a supported file type/)).toBeInTheDocument();
    await user.upload(input, png("huge.png", 10 * 1024 * 1024 + 1));
    expect(await screen.findByText(/"huge.png" is too large/)).toBeInTheDocument();
    await user.upload(input, [1, 2, 3, 4, 5, 6].map((n) => png(`p${n}.png`)));
    expect(await screen.findByText(/"p6.png" exceeds the maximum number of files/)).toBeInTheDocument();
  });

  it("submits values, selected images and the captcha token; shows a safe receipt", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ id: "secret-id", created_at: "x" });
    mocked.mockReturnValue({ mutateAsync } as never);
    render(<BringYourIdeaForm />);
    await fillRequired(user);
    await user.type(screen.getByLabelText("Dimensions (optional)"), "20 cm tall");
    await user.upload(screen.getByLabelText("Reference images (optional)"), png("sketch.png"));
    await user.click(screen.getByRole("button", { name: "Send my idea" }));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    const arg = mutateAsync.mock.calls[0]![0];
    expect(arg.captchaToken).toBe(FAKE_CAPTCHA_TOKEN);
    expect(arg.values).toMatchObject({ name: "Rana", phone: "+961 70 123 456", project_title: "Cedar lamp", dimensions: "20 cm tall", preferred_material: "" });
    expect(arg.attachments.map((f: File) => f.name)).toEqual(["sketch.png"]);
    expect(await screen.findByText(/we've received your idea/i)).toBeInTheDocument();
    expect(screen.queryByText(/secret-id/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Send another idea" }));
    expect(screen.getByLabelText("Name")).toHaveValue("");
    expect(screen.queryByText("sketch.png")).not.toBeInTheDocument();
  });

  it("names a server-rejected image, keeps the form, and retries with a fresh token", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi
      .fn()
      .mockRejectedValueOnce({
        kind: "http",
        status: 422,
        code: "UPLOAD_REJECTED",
        detail: "RAW",
        errors: [{ loc: ["body", "attachments", 0], msg: "RAW MSG", type: "value_error" }],
        message: "x",
        raw: {},
      })
      .mockResolvedValueOnce({ id: "m", created_at: "x" });
    mocked.mockReturnValue({ mutateAsync } as never);
    render(<BringYourIdeaForm />);
    await fillRequired(user);
    await user.upload(screen.getByLabelText("Reference images (optional)"), png("fake.png"));
    await user.click(screen.getByRole("button", { name: "Send my idea" }));
    expect(await screen.findByText(/“fake.png” couldn't be accepted/)).toBeInTheDocument();
    expect(screen.queryByText(/RAW/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Project title")).toHaveValue("Cedar lamp");
    expect(fakeCaptcha.resetCount).toBe(1);
    await user.click(screen.getByRole("button", { name: "Remove fake.png" }));
    await user.click(screen.getByRole("button", { name: "Send my idea" }));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(2));
    expect(mutateAsync.mock.calls[1]![0].attachments).toEqual([]);
  });

  it("shows captcha copy on refusal and refuses to send without a token", async () => {
    fakeCaptcha.autoIssue = false;
    const user = userEvent.setup();
    const mutateAsync = vi.fn();
    mocked.mockReturnValue({ mutateAsync } as never);
    render(<BringYourIdeaForm />);
    await fillRequired(user);
    await user.click(screen.getByRole("button", { name: "Send my idea" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(CAPTCHA_FAILURE_COPY.missing);
    expect(mutateAsync).not.toHaveBeenCalled();
  });
});
