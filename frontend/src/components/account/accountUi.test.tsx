import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  AccountBackLink,
  AccountErrorCard,
  AccountListSkeleton,
  AccountSection,
  AccountSessionCard,
  AccountThumb,
} from "./accountUi";

// Redesign Batch 7 — the shared account presentation blocks own no logic;
// these pin their accessibility contract.
describe("accountUi", () => {
  it("AccountSection is a region named by its visible h2 (the icon is decorative)", () => {
    render(
      <AccountSection title="Payment" icon="payments">
        <p>Body</p>
      </AccountSection>
    );
    const region = screen.getByRole("region", { name: "Payment" });
    expect(region).toContainElement(screen.getByRole("heading", { level: 2, name: "Payment" }));
    expect(region.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it("AccountListSkeleton is one labelled status", () => {
    render(<AccountListSkeleton label="Loading your orders…" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading your orders…");
  });

  it("AccountErrorCard announces the message with its retry", async () => {
    const onRetry = vi.fn();
    render(<AccountErrorCard message="We couldn't load this." onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("We couldn't load this.");
    await userEvent.setup().click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("AccountSessionCard links to sign-in", () => {
    render(<AccountSessionCard message="Your session has expired." href="/login?returnTo=%2Faccount" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Your session has expired.");
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login?returnTo=%2Faccount");
  });

  it("AccountBackLink keeps its source-case accessible name", () => {
    render(<AccountBackLink href="/account/orders">Back to your orders</AccountBackLink>);
    expect(screen.getByRole("link", { name: "Back to your orders" })).toHaveAttribute("href", "/account/orders");
  });

  it("AccountThumb is decorative with or without an image", () => {
    const { container, rerender } = render(<AccountThumb src="/a.png" fallbackIcon="image" />);
    expect(container.firstElementChild).toHaveAttribute("aria-hidden", "true");
    expect(container.querySelector("img")).toHaveAttribute("alt", "");
    rerender(<AccountThumb src={null} fallbackIcon="deployed-code" />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("svg")).toHaveAttribute("data-icon", "deployed-code");
  });
});
