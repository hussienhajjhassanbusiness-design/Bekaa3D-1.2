import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Toast } from "./Toast";

describe("Toast", () => {
  it("renders the message text", () => {
    render(<Toast message="Saved successfully" variant="success" />);

    expect(screen.getByText("Saved successfully")).toBeInTheDocument();
  });

  it("uses role=status and aria-live=polite — never role=alert — regardless of variant", () => {
    render(<Toast message="Something failed" variant="error" />);

    const toast = screen.getByRole("status");
    expect(toast).toHaveAttribute("aria-live", "polite");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it.each([
    ["success", "bg-success-bg"],
    ["error", "bg-danger-bg"],
    ["info", "bg-info-bg"],
  ] as const)(
    "applies the mapped semantic token background class for the '%s' variant",
    (variant, expectedClassFragment) => {
      render(<Toast message="Variant check" variant={variant} />);

      expect(screen.getByRole("status").className).toContain(expectedClassFragment);
    }
  );

  it("renders no dismiss control when onDismiss is not supplied", () => {
    render(<Toast message="No dismiss" variant="info" />);

    expect(screen.queryByRole("button")).toBeNull();
  });

  it("renders a dismiss control with a meaningful accessible name when onDismiss is supplied", () => {
    render(<Toast message="Dismissible" variant="info" onDismiss={() => {}} />);

    expect(screen.getByRole("button", { name: "Dismiss notification" })).toBeInTheDocument();
  });

  it("invokes the supplied onDismiss callback when the dismiss control is activated", async () => {
    const user = userEvent.setup();
    const onDismiss = vi.fn();
    render(<Toast message="Click to dismiss" variant="success" onDismiss={onDismiss} />);

    await user.click(screen.getByRole("button", { name: "Dismiss notification" }));

    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("carries the motion-reduce structural contract on its transition classes (structural only — jsdom cannot evaluate the actual media query)", () => {
    render(<Toast message="Motion check" variant="success" />);

    expect(screen.getByRole("status").className).toContain("motion-reduce:transition-none");
  });
});
