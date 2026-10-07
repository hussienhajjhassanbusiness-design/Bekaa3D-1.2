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

  it("renders only decorative background elements, all aria-hidden", () => {
    const { container } = render(<Home />);

    const decorative = container.querySelectorAll('[aria-hidden="true"]');
    for (const el of decorative) {
      expect(el).toHaveAttribute("aria-hidden", "true");
    }
  });
});
