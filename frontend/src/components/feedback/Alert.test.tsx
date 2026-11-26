import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Alert } from "./Alert";

describe("Alert", () => {
  it("renders the message", () => {
    render(<Alert message="Check your email to continue." variant="success" />);

    expect(screen.getByText("Check your email to continue.")).toBeInTheDocument();
  });

  // DESIGN-SYSTEM §9 status colours on Stitch MD3 containers, plus a
  // decorative per-variant icon (different shape, not colour alone).
  it.each([
    ["success", "bg-secondary-container/40", "check-circle"],
    ["info", "bg-info-container", "info"],
    ["warning", "bg-warning-container", "warning"],
    ["error", "bg-error-container", "error"],
  ] as const)("applies the mapped status container and icon for the '%s' variant", (variant, expectedClassFragment, iconName) => {
    render(<Alert message="Variant check" variant={variant} />);

    const region = variant === "error" ? screen.getByRole("alert") : screen.getByRole("status");
    expect(region.className).toContain(expectedClassFragment);
    const icon = region.querySelector(`svg[data-icon="${iconName}"]`);
    expect(icon).not.toBeNull();
    expect(icon).toHaveAttribute("aria-hidden", "true");
  });

  it.each(["success", "info", "warning"] as const)(
    "uses role=status/aria-live=polite for the non-urgent '%s' variant",
    (variant) => {
      render(<Alert message="Non-urgent" variant={variant} />);

      const region = screen.getByRole("status");
      expect(region).toHaveAttribute("aria-live", "polite");
      expect(screen.queryByRole("alert")).toBeNull();
    }
  );

  it("uses role=alert/aria-live=assertive for the urgent 'error' variant", () => {
    render(<Alert message="Something failed" variant="error" />);

    const region = screen.getByRole("alert");
    expect(region).toHaveAttribute("aria-live", "assertive");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("never renders a dismiss control — Alert is persistent page-level feedback, not a transient Toast", () => {
    render(<Alert message="Persistent message" variant="info" />);

    expect(screen.queryByRole("button")).toBeNull();
  });
});
