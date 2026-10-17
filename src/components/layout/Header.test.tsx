import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { usePathname } from "next/navigation";
import { Header } from "./Header";

vi.mock("next/navigation", () => ({ usePathname: vi.fn(() => "/") }));
const mockedUsePathname = vi.mocked(usePathname);

describe("Header", () => {
  it("renders the Bekaa3D brand-mark text as a link to /", () => {
    render(<Header />);

    const brandLink = screen.getByRole("link", { name: "Bekaa3D" });
    expect(brandLink).toHaveAttribute("href", "/");
  });

  it("does not render its own <header> landmark — AppLayout already owns that landmark", () => {
    const { container } = render(<Header />);

    expect(container.querySelector("header")).toBeNull();
  });

  it("renders real navigation links only to mounted routes (/, /shop, /about)", () => {
    render(<Header />);

    const nav = screen.getAllByRole("navigation", { name: "Main" })[0]!;
    expect(nav).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Shop" })[0]).toHaveAttribute("href", "/shop");
    expect(screen.getAllByRole("link", { name: "About" })[0]).toHaveAttribute("href", "/about");
  });

  it("marks the current route's nav link with aria-current", () => {
    mockedUsePathname.mockReturnValue("/shop");
    render(<Header />);

    expect(screen.getAllByRole("link", { name: "Shop" })[0]).toHaveAttribute("aria-current", "page");
    expect(screen.getAllByRole("link", { name: "Home" })[0]).not.toHaveAttribute("aria-current");
  });

  it("the mobile menu toggle is closed by default and opens the nav list on click", async () => {
    render(<Header />);

    const toggle = screen.getByRole("button", { name: /open menu/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();

    await userEvent.click(toggle);
    expect(screen.getByRole("button", { name: /close menu/i })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByRole("navigation", { name: "Main" })).toHaveLength(2);
  });

  it("does not render an actual logo image asset", () => {
    const { container } = render(<Header />);

    expect(container.querySelector("img")).toBeNull();
  });
});
