import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PasswordField } from "./PasswordField";

describe("PasswordField", () => {
  it("starts with the input hidden (type=password)", () => {
    render(<PasswordField label="Password" />);

    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
  });

  it("renders a real type=button toggle with an initial accessible name and aria-pressed=false", () => {
    render(<PasswordField label="Password" />);

    const toggle = screen.getByRole("button", { name: "Show password" });
    expect(toggle).toHaveAttribute("type", "button");
    expect(toggle).toHaveAttribute("aria-pressed", "false");
  });

  it("activating the toggle reveals the password, flips the accessible name, and sets aria-pressed=true", async () => {
    const user = userEvent.setup();
    render(<PasswordField label="Password" />);

    await user.click(screen.getByRole("button", { name: "Show password" }));

    const input = screen.getByLabelText("Password");
    expect(input).toHaveAttribute("type", "text");
    const toggle = screen.getByRole("button", { name: "Hide password" });
    expect(toggle).toHaveAttribute("aria-pressed", "true");
  });

  it("activating the toggle twice returns to hidden", async () => {
    const user = userEvent.setup();
    render(<PasswordField label="Password" />);

    await user.click(screen.getByRole("button", { name: "Show password" }));
    await user.click(screen.getByRole("button", { name: "Hide password" }));

    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
  });

  it("preserves the typed value across the visibility toggle", async () => {
    const user = userEvent.setup();
    render(<PasswordField label="Password" />);

    const input = screen.getByLabelText("Password");
    await user.type(input, "correct-horse-battery-staple");
    expect(input).toHaveValue("correct-horse-battery-staple");

    await user.click(screen.getByRole("button", { name: "Show password" }));

    expect(screen.getByLabelText("Password")).toHaveValue("correct-horse-battery-staple");
  });

  it("the toggle is keyboard-operable", async () => {
    const user = userEvent.setup();
    render(<PasswordField label="Password" />);

    await user.tab(); // to the input
    await user.tab(); // to the toggle button
    const toggle = screen.getByRole("button", { name: "Show password" });
    expect(toggle).toHaveFocus();

    await user.keyboard("{Enter}");
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "text");
  });

  it("renders a static hint and links it via aria-describedby", () => {
    render(<PasswordField label="Password" hint="Use at least one number and one letter." />);

    const input = screen.getByLabelText("Password");
    const describedBy = input.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    const ids = describedBy!.split(" ");
    const texts = ids.map((id) => document.getElementById(id)?.textContent);
    expect(texts).toContain("Use at least one number and one letter.");
  });

  it("links both hint and error simultaneously via aria-describedby", () => {
    render(<PasswordField label="Password" hint="Helper text" error="Field error" />);

    const input = screen.getByLabelText("Password");
    const ids = input.getAttribute("aria-describedby")!.split(" ");
    expect(ids).toHaveLength(2);
    const texts = ids.map((id) => document.getElementById(id)?.textContent);
    expect(texts).toContain("Helper text");
    expect(texts).toContain("Field error");
  });

  it("sets aria-invalid when an error is present", () => {
    render(<PasswordField label="Password" error="Password is required." />);

    expect(screen.getByLabelText("Password")).toHaveAttribute("aria-invalid", "true");
  });
});
