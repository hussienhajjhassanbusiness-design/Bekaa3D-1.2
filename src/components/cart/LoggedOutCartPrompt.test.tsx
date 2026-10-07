import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { LoggedOutCartPrompt } from "./LoggedOutCartPrompt";
import { buildLoginRedirectPath } from "@/lib/auth/returnTo";

// FVS-025-IMPLEMENTATION-PLAN.md T04 — resolves the /cart anonymous-
// visitor discrepancy (plan §0): this belongs to MiniCartDrawer, not
// the protected /cart page. Reuses buildLoginRedirectPath directly
// (FVS-003) rather than duplicating redirect-safety logic. No
// guest-cart affordance of any kind.

describe("LoggedOutCartPrompt", () => {
  it("renders a real link to the login page with the default /cart returnTo", () => {
    render(<LoggedOutCartPrompt />);
    expect(screen.getByRole("link", { name: /log in/i })).toHaveAttribute("href", buildLoginRedirectPath("/cart"));
  });

  it("uses a caller-supplied returnToPath when given", () => {
    render(<LoggedOutCartPrompt returnToPath="/cart/checkout-entry" />);
    expect(screen.getByRole("link", { name: /log in/i })).toHaveAttribute(
      "href",
      buildLoginRedirectPath("/cart/checkout-entry")
    );
  });

  it("has no guest-cart affordance — no form, no button of any kind", () => {
    const { container } = render(<LoggedOutCartPrompt />);
    expect(container.querySelector("form")).toBeNull();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<LoggedOutCartPrompt />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
