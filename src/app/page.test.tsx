import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import Home from "./page";

describe("Home (root route /)", () => {
  it("renders through AppLayout with exactly one banner, one main, and one contentinfo landmark", () => {
    render(<Home />);

    expect(screen.getAllByRole("banner")).toHaveLength(1);
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getAllByRole("contentinfo")).toHaveLength(1);
  });

  it("composes the Header/Footer skeleton (both render the Bekaa3D brand mark)", () => {
    render(<Home />);

    expect(screen.getByRole("banner")).toHaveTextContent("Bekaa3D");
    expect(screen.getByRole("contentinfo")).toHaveTextContent("Bekaa3D");
  });

  it("renders FVS-001 foundation-slice placeholder content inside <main>, not real Home content", () => {
    render(<Home />);

    const main = within(screen.getByRole("main"));
    expect(
      main.getByRole("heading", { name: /Bekaa3D — Engineered Grade 3D Solutions/i })
    ).toBeInTheDocument();
    expect(main.getByText(/foundation slice/i)).toBeInTheDocument();
  });

  it("contains no navigation, product, or commerce content — this is not the real Home page", () => {
    const { container } = render(<Home />);

    expect(container.querySelector("nav")).toBeNull();
    // AppLayout always renders SkipLink (itself a link) — that's structural
    // shell behavior, not "business navigation." No *other* link exists.
    expect(screen.getAllByRole("link")).toHaveLength(1);
    expect(screen.getByRole("link")).toHaveAccessibleName("Skip to main content");
    expect(screen.queryByRole("button")).toBeNull();
  });
});
