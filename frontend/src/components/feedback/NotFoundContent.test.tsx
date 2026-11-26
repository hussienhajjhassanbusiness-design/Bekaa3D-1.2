import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { NotFoundContent } from "./NotFoundContent";

// FVS-029-IMPLEMENTATION-PLAN.md T06 — extracted from src/app/not-found.tsx
// (its own prior comment said extraction was YAGNI "no known reuse
// case yet" — OrderDetail's foreign/nonexistent-order case is the
// second real use case, justifying it now). This file's assertions
// mirror src/app/not-found.test.tsx's own exactly, proving the
// extraction changes nothing about the rendered output.

describe("NotFoundContent", () => {
  it("renders a clear 404/not-found heading and explanatory text", () => {
    render(<NotFoundContent />);

    expect(screen.getByRole("heading", { name: /page not found/i })).toBeInTheDocument();
    expect(screen.getByText(/doesn.t exist|couldn.t find|been moved/i)).toBeInTheDocument();
  });

  it("provides a real link back to / with a meaningful accessible name", () => {
    render(<NotFoundContent />);

    const homeLink = screen.getByRole("link", { name: /back to home/i });
    expect(homeLink).toHaveAttribute("href", "/");
  });

  it("introduces no product/catalogue links or other business content", () => {
    render(<NotFoundContent />);

    expect(screen.getAllByRole("link")).toHaveLength(1);
    expect(screen.queryByRole("button")).toBeNull();
  });
});
