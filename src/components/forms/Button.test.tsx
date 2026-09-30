import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Button } from "./Button";

describe("Button", () => {
  it("renders its children", () => {
    render(<Button>Submit</Button>);

    expect(screen.getByRole("button", { name: "Submit" })).toBeInTheDocument();
  });

  it("defaults to type=button (never accidentally submits a form)", () => {
    render(<Button>Click me</Button>);

    expect(screen.getByRole("button")).toHaveAttribute("type", "button");
  });

  it("accepts an explicit type=submit", () => {
    render(<Button type="submit">Save</Button>);

    expect(screen.getByRole("button")).toHaveAttribute("type", "submit");
  });

  it("calls onClick when clicked", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Go</Button>);

    await user.click(screen.getByRole("button"));

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("is disabled when disabled is passed, and does not fire onClick", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        Go
      </Button>
    );

    const button = screen.getByRole("button");
    expect(button).toBeDisabled();
    await user.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("isLoading disables the button and exposes aria-busy, preventing double activation", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <Button isLoading onClick={onClick}>
        Submitting
      </Button>
    );

    const button = screen.getByRole("button");
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    await user.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("does not expose aria-busy when not loading", () => {
    render(<Button>Go</Button>);

    expect(screen.getByRole("button")).not.toHaveAttribute("aria-busy");
  });
});
