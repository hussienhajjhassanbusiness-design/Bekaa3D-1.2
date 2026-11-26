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

  it("defaults to the primary (brand) visual treatment", () => {
    render(<Button>Save</Button>);
    expect(screen.getByRole("button")).toHaveClass("bg-primary", "text-on-primary");
  });

  it("variant='destructive' renders the danger treatment, never the primary brand color", () => {
    render(<Button variant="destructive">Delete</Button>);
    const button = screen.getByRole("button");
    expect(button).toHaveClass("bg-error");
    expect(button).not.toHaveClass("bg-primary");
  });

  it("variant='secondary' is an outline brand button (Stitch secondary = 2px primary outline), never solid", () => {
    render(<Button variant="secondary">Edit</Button>);
    const button = screen.getByRole("button");
    expect(button).toHaveClass("border-primary", "text-primary", "bg-transparent");
    expect(button).not.toHaveClass("bg-primary");
  });

  it("variant='outline' is the neutral outline, and variant='ghost' has no fill or border colour", () => {
    const { rerender } = render(<Button variant="outline">Cancel</Button>);
    expect(screen.getByRole("button")).toHaveClass("border-outline-variant", "text-on-surface");
    expect(screen.getByRole("button")).not.toHaveClass("bg-primary");

    rerender(<Button variant="ghost">More</Button>);
    expect(screen.getByRole("button")).toHaveClass("border-transparent", "bg-transparent", "text-primary");
  });

  it("defaults to the md size (44px minimum height) and accepts sm / lg", () => {
    const { rerender } = render(<Button>Go</Button>);
    expect(screen.getByRole("button")).toHaveClass("min-h-11");

    rerender(<Button size="sm">Go</Button>);
    expect(screen.getByRole("button")).toHaveClass("min-h-9");

    rerender(<Button size="lg">Go</Button>);
    expect(screen.getByRole("button")).toHaveClass("min-h-13");
  });

  it("shows a decorative spinner while loading and keeps the label (accessible name unchanged)", () => {
    const { rerender } = render(<Button>Place order</Button>);
    expect(screen.queryByTestId("button-spinner")).toBeNull();

    rerender(<Button isLoading>Place order</Button>);
    const button = screen.getByRole("button", { name: "Place order" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(screen.getByTestId("button-spinner")).toHaveAttribute("aria-hidden", "true");
  });

  it("keeps the press-scale effect off for disabled buttons and under reduced motion", () => {
    render(<Button disabled>Go</Button>);
    const button = screen.getByRole("button");
    expect(button).toHaveClass("enabled:active:scale-95", "motion-reduce:enabled:active:scale-100");
    expect(button).not.toHaveClass("active:scale-95");
  });
});
