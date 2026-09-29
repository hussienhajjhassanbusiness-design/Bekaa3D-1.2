import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SkipLink } from "./SkipLink";

describe("SkipLink", () => {
  it("renders an accessible link named 'Skip to main content'", () => {
    render(<SkipLink />);

    expect(
      screen.getByRole("link", { name: "Skip to main content" })
    ).toBeInTheDocument();
  });

  it("targets #main-content via its href", () => {
    render(<SkipLink />);

    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveAttribute(
      "href",
      "#main-content"
    );
  });

  it("moves keyboard focus to the #main-content target when activated", async () => {
    // A same-page fragment link does not reliably move keyboard focus to its
    // target in every browser (some engines only scroll, they don't focus)
    // — SkipLink's job includes guaranteeing focus transfer itself, not just
    // relying on default anchor-navigation. This test renders a minimal
    // local #main-content fixture (not the real AppLayout) to prove that
    // contract in isolation; AppLayout.test.tsx separately proves the real
    // <main> it renders carries the same id/tabIndex contract this depends on.
    const user = userEvent.setup();
    render(
      <>
        <SkipLink />
        <main id="main-content" tabIndex={-1}>
          Content
        </main>
      </>
    );

    await user.click(screen.getByRole("link", { name: "Skip to main content" }));

    expect(document.getElementById("main-content")).toHaveFocus();
  });

  it("carries the structural class contract for being visually hidden until focused", () => {
    // jsdom does not apply real CSS pseudo-class-driven visibility, so this
    // only proves the *contract* (sr-only by default, not-sr-only on focus)
    // exists in markup — not that it actually renders off-screen-then-visible
    // in a browser. That is verified separately by manual/CSS inspection.
    render(<SkipLink />);

    const link = screen.getByRole("link", { name: "Skip to main content" });
    expect(link).toHaveClass("sr-only");
    expect(link).toHaveClass("focus:not-sr-only");
  });
});
