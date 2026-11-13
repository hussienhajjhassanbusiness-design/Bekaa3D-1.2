import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { RatingSummary } from "./RatingSummary";

describe("RatingSummary", () => {
  it("renders nothing without reviews (no fake '(0)' widget)", () => {
    const { container } = render(<RatingSummary averageRating={0} reviewCount={0} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("is spoken once as a sentence; the compact visual is hidden from assistive tech", () => {
    const { container } = render(<RatingSummary averageRating={4.25} reviewCount={12} />);
    expect(screen.getByText("Rated 4.3 out of 5 from 12 reviews")).toHaveClass("sr-only");
    expect(container.querySelector('[aria-hidden="true"]')).toHaveTextContent("4.3(12)");
  });

  it("uses the singular for one review and spells out reviews at the detail size", () => {
    render(<RatingSummary averageRating={5} reviewCount={1} size="md" />);
    expect(screen.getByText("Rated 5.0 out of 5 from 1 review")).toBeInTheDocument();
    expect(screen.getByText("(1 review)")).toBeInTheDocument();
  });
});
