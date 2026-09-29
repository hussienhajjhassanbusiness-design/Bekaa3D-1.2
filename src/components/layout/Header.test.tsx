import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Header } from "./Header";

describe("Header", () => {
  it("renders the Bekaa3D brand-mark text", () => {
    render(<Header />);

    expect(screen.getByText("Bekaa3D")).toBeInTheDocument();
  });

  it("does not render its own <header> landmark — AppLayout already owns that landmark", () => {
    const { container } = render(<Header />);

    expect(container.querySelector("header")).toBeNull();
  });

  it("contains no navigation structure", () => {
    const { container } = render(<Header />);

    expect(container.querySelector("nav")).toBeNull();
    expect(container.querySelector('[role="navigation"]')).toBeNull();
  });

  it("contains no interactive controls (no hamburger, no menu button, no links)", () => {
    const { container } = render(<Header />);

    expect(container.querySelector("button")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
  });

  it("does not render an actual logo image asset", () => {
    const { container } = render(<Header />);

    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("svg")).toBeNull();
  });
});
