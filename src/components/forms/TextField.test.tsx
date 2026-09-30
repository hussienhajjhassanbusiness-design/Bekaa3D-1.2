import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TextField } from "./TextField";

describe("TextField", () => {
  it("renders a visible label associated with the input", () => {
    render(<TextField label="Email address" />);

    expect(screen.getByLabelText("Email address")).toBeInTheDocument();
  });

  it("renders hint text and links it via aria-describedby", () => {
    render(<TextField label="Email address" hint="We'll never share this." />);

    const input = screen.getByLabelText("Email address");
    const describedBy = input.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    const [hintId] = describedBy!.split(" ");
    const hintEl = document.getElementById(hintId ?? "");
    expect(hintEl).toHaveTextContent("We'll never share this.");
  });

  it("renders error text, links it via aria-describedby, and sets aria-invalid", () => {
    render(<TextField label="Email address" error="Enter a valid email." />);

    const input = screen.getByLabelText("Email address");
    expect(input).toHaveAttribute("aria-invalid", "true");
    const describedBy = input.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    const ids = describedBy!.split(" ");
    const errorEl = ids.map((id) => document.getElementById(id)).find((el) => el?.textContent === "Enter a valid email.");
    expect(errorEl).toBeTruthy();
  });

  it("does not set aria-invalid when there is no error", () => {
    render(<TextField label="Email address" />);

    expect(screen.getByLabelText("Email address")).not.toHaveAttribute("aria-invalid");
  });

  it("links both hint and error simultaneously via aria-describedby when both are present", () => {
    render(<TextField label="Email address" hint="Helper text" error="Field error" />);

    const input = screen.getByLabelText("Email address");
    const ids = input.getAttribute("aria-describedby")!.split(" ");
    expect(ids).toHaveLength(2);
    const texts = ids.map((id) => document.getElementById(id)?.textContent);
    expect(texts).toContain("Helper text");
    expect(texts).toContain("Field error");
  });

  it("passes through native input props and accepts typed input", async () => {
    const user = userEvent.setup();
    render(<TextField label="Email address" type="email" placeholder="you@example.com" />);

    const input = screen.getByLabelText("Email address");
    expect(input).toHaveAttribute("type", "email");
    expect(input).toHaveAttribute("placeholder", "you@example.com");

    await user.type(input, "test@example.com");
    expect(input).toHaveValue("test@example.com");
  });
});
