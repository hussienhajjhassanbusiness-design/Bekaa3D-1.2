import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import Home from "./page";

// FVS001-T14: the AppLayout/Header/Footer shell is now owned by the root
// layout (see src/app/layout.test.tsx for the composed-shell landmark
// assertions) — this file tests only Home's own page content, not shell
// ownership it no longer has.
describe("Home (root route /)", () => {
  it("renders FVS-001 foundation-slice placeholder content, not real Home content", () => {
    render(<Home />);

    expect(
      screen.getByRole("heading", { name: /Bekaa3D — Engineered Grade 3D Solutions/i })
    ).toBeInTheDocument();
    expect(screen.getByText(/foundation slice/i)).toBeInTheDocument();
  });

  it("contains no navigation, product, or commerce content — this is not the real Home page", () => {
    const { container } = render(<Home />);

    expect(container.querySelector("nav")).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
