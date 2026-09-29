import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import NotFound from "./not-found";

// FVS001-T14: the AppLayout/Header/Footer shell is now owned by the root
// layout (see src/app/layout.test.tsx for the composed-shell landmark
// assertions) — this file tests only NotFound's own content, not shell
// ownership it no longer has.
describe("NotFound (catch-all 404)", () => {
  it("renders a clear 404/not-found heading and explanatory text", () => {
    render(<NotFound />);

    expect(screen.getByRole("heading", { name: /page not found/i })).toBeInTheDocument();
    expect(
      screen.getByText(/doesn.t exist|couldn.t find|been moved/i)
    ).toBeInTheDocument();
  });

  it("provides a real link back to / with a meaningful accessible name", () => {
    render(<NotFound />);

    const homeLink = screen.getByRole("link", { name: /back to home/i });
    expect(homeLink).toHaveAttribute("href", "/");
  });

  it("introduces no product/catalogue links or other business content", () => {
    render(<NotFound />);

    // Exactly one link is expected: this page's own back-to-home link.
    // SkipLink is no longer rendered here — it's the root layout's
    // AppLayout that owns it now (FVS001-T14).
    expect(screen.getAllByRole("link")).toHaveLength(1);
    expect(screen.queryByRole("button")).toBeNull();
  });
});
