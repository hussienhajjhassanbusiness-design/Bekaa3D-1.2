import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Footer } from "./Footer";

describe("Footer", () => {
  it("renders the Bekaa3D brand-mark text", () => {
    render(<Footer />);

    expect(screen.getByText("Bekaa3D")).toBeInTheDocument();
  });

  it("does not render its own <footer> landmark — AppLayout already owns that landmark", () => {
    const { container } = render(<Footer />);

    expect(container.querySelector("footer")).toBeNull();
  });

  it("links only to routes actually mounted this phase (/shop, /about) — no invented legal/social links", () => {
    render(<Footer />);

    expect(screen.getByRole("link", { name: "Shop" })).toHaveAttribute("href", "/shop");
    expect(screen.getByRole("link", { name: "About" })).toHaveAttribute("href", "/about");
    expect(screen.getAllByRole("link")).toHaveLength(2);
  });

  it("does not render an actual logo image asset", () => {
    const { container } = render(<Footer />);

    expect(container.querySelector("img")).toBeNull();
  });
});
