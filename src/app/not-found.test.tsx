import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import NotFound from "./not-found";

describe("NotFound (catch-all 404)", () => {
  it("renders through the same AppLayout shell: exactly one banner, one main, and one contentinfo landmark", () => {
    render(<NotFound />);

    expect(screen.getAllByRole("banner")).toHaveLength(1);
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getAllByRole("contentinfo")).toHaveLength(1);
  });

  it("renders a clear 404/not-found heading and explanatory text inside <main>", () => {
    render(<NotFound />);

    const main = within(screen.getByRole("main"));
    expect(main.getByRole("heading", { name: /page not found/i })).toBeInTheDocument();
    expect(
      main.getByText(/doesn.t exist|couldn.t find|been moved/i)
    ).toBeInTheDocument();
  });

  it("provides a real link back to / with a meaningful accessible name", () => {
    render(<NotFound />);

    const homeLink = screen.getByRole("link", { name: /back to home/i });
    expect(homeLink).toHaveAttribute("href", "/");
  });

  it("introduces no product/catalogue links or other business content", () => {
    render(<NotFound />);

    // Exactly two links are expected in total: AppLayout's own SkipLink
    // (structural shell behavior, present on every page) and this page's
    // one back-to-home link. No third/business link exists.
    expect(screen.getAllByRole("link")).toHaveLength(2);
    expect(screen.queryByRole("button")).toBeNull();
  });
});
