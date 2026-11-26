import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { Footer } from "./Footer";

describe("Footer", () => {
  it("renders the Bekaa3D brand-mark text (not a link — the header owns the home link)", () => {
    render(<Footer />);

    expect(screen.getByText("Bekaa3D")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Bekaa3D" })).not.toBeInTheDocument();
  });

  it("does not render its own <footer> landmark — AppLayout already owns that landmark", () => {
    const { container } = render(<Footer />);

    expect(container.querySelector("footer")).toBeNull();
  });

  it("links only to routes actually mounted — no invented legal, social, newsletter or payment links", () => {
    render(<Footer />);

    const nav = screen.getByRole("navigation", { name: "Footer" });
    const hrefs = within(nav)
      .getAllByRole("link")
      .map((link) => [link.textContent, link.getAttribute("href")]);
    expect(hrefs).toEqual([
      ["Shop", "/shop"],
      ["Bring your idea", "/bring-your-idea"],
      ["About", "/about"],
      ["Contact", "/contact"],
      ["My account", "/account"],
      ["Wishlist", "/account/wishlist"],
      ["Cart", "/cart"],
    ]);
    // Every link lives in the labelled footer nav.
    expect(screen.getAllByRole("link")).toHaveLength(7);
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByText(/privacy|terms|newsletter|subscribe/i)).not.toBeInTheDocument();
  });

  it("never links into the admin area", () => {
    render(<Footer />);

    for (const link of screen.getAllByRole("link")) {
      expect(link.getAttribute("href")).not.toMatch(/^\/admin/);
    }
  });

  it("groups the links under headed lists", () => {
    render(<Footer />);

    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual(["Shop", "Company", "Your account"]);
    expect(screen.getAllByRole("list")).toHaveLength(3);
  });

  it("shows the real logo mark as a decorative image (the wordmark text names the brand)", () => {
    const { container } = render(<Footer />);

    const logo = container.querySelector("img");
    expect(logo).toHaveAttribute("src", "/brand/bekaa3d-mark.png");
    expect(logo).toHaveAttribute("alt", "");
  });

  it("shows the current year in the copyright line", () => {
    render(<Footer />);

    expect(screen.getByText(`© ${new Date().getFullYear()} Bekaa3D. All rights reserved.`)).toBeInTheDocument();
  });
});
