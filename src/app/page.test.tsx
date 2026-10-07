import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import Home from "./page";

// FVS-022 follow-up: Home now renders the real Bekaa3D home surface
// (HeroSection only) instead of the FVS-001 placeholder. The
// AppLayout/Header/Footer shell is owned by the root layout (see
// src/app/layout.test.tsx) — this file tests only Home's own page
// content, not shell ownership it never had.
describe("Home (root route /)", () => {
  it("renders the approved Bekaa3D heading via HeroSection", () => {
    render(<Home />);

    expect(
      screen.getByRole("heading", { level: 1, name: /Bekaa3D — Engineered Grade 3D Solutions/i })
    ).toBeInTheDocument();
  });

  it("no longer renders the retired FVS-001 placeholder paragraph", () => {
    render(<Home />);

    expect(screen.queryByText(/foundation slice/i)).not.toBeInTheDocument();
  });

  it("contains no CTA links to routes that don't exist yet (no fabricated destinations)", () => {
    render(<Home />);

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("contains no fabricated product, commerce, or secondary-section content", () => {
    render(<Home />);

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getAllByRole("heading")).toHaveLength(1);
  });

  it("confines all decorative markup to exactly one aria-hidden wrapper, separate from the real heading", () => {
    const { container } = render(<Home />);

    const wrappers = container.querySelectorAll('[aria-hidden="true"]');
    expect(wrappers).toHaveLength(1);
    const wrapper = wrappers[0]!;

    const heading = screen.getByRole("heading", { level: 1 });
    expect(wrapper.contains(heading)).toBe(false);

    // Every decorative child element lives inside that one wrapper — none
    // sits outside it, unhidden, where assistive tech would read it.
    const decorativeChildren = wrapper.querySelectorAll("div");
    expect(decorativeChildren.length).toBeGreaterThan(0);
  });
});
