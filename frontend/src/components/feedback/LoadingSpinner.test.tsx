import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { LoadingSpinner } from "./LoadingSpinner";

describe("LoadingSpinner", () => {
  it("renders a status region with the accessible name 'Loading…'", () => {
    render(<LoadingSpinner />);

    // role="status" is the accessible-status contract; its accessible name
    // must be exactly the loading text, with nothing else (e.g. leaked SVG
    // content) contributing to it.
    const status = screen.getByRole("status");
    expect(status).toHaveAccessibleName("Loading…");
  });

  it("hides the accessible loading text visually but keeps it in the accessibility tree", () => {
    render(<LoadingSpinner />);

    // getByText only finds text that is actually present in the DOM (as
    // opposed to aria-hidden content), which is exactly what a visually-
    // hidden ("sr-only") technique should produce: present for assistive
    // tech, not painted on screen.
    const hiddenText = screen.getByText("Loading…");
    expect(hiddenText).toHaveClass("sr-only");
  });

  it("hides the decorative spinner graphic from assistive technology", () => {
    const { container } = render(<LoadingSpinner />);

    const decorative = container.querySelector("svg");
    expect(decorative).not.toBeNull();
    expect(decorative).toHaveAttribute("aria-hidden", "true");
  });

  it("carries the structural class contract for reduced-motion behavior", () => {
    // jsdom does not evaluate `prefers-reduced-motion` media queries, so
    // this only proves the *contract* exists in markup (the animate-spin
    // class plus a motion-reduce override class) — it does not, and cannot,
    // prove that a browser actually suppresses the animation under the
    // media query. That is verified separately by inspecting the compiled
    // CSS/Tailwind output, not by this test.
    const { container } = render(<LoadingSpinner />);

    const animated = container.querySelector("svg");
    expect(animated).toHaveClass("animate-spin");
    expect(animated).toHaveClass("motion-reduce:animate-none");
  });
});
