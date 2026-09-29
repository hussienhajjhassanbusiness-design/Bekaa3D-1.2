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

  it("contains no speculative business content (no nav, no links, no legal/social content)", () => {
    const { container } = render(<Footer />);

    expect(container.querySelector("nav")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    expect(container.querySelector("button")).toBeNull();
  });

  it("contains no interactive future placeholders", () => {
    const { container } = render(<Footer />);

    expect(container.querySelectorAll("button, a, input, select, textarea")).toHaveLength(0);
  });

  it("does not render an actual logo image asset", () => {
    const { container } = render(<Footer />);

    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("svg")).toBeNull();
  });
});
