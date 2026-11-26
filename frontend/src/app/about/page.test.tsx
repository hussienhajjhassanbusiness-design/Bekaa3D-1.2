import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import AboutPage from "./page";

describe("AboutPage", () => {
  it("renders a real heading and static brand copy", () => {
    render(<AboutPage />);

    expect(screen.getByRole("heading", { name: "About Bekaa3D" })).toBeInTheDocument();
    expect(screen.getByText("Engineered Grade 3D Solutions.")).toBeInTheDocument();
  });

  it("never fabricates testimonials, customer counts, or review content", () => {
    render(<AboutPage />);

    expect(screen.queryByText(/customers|reviews|testimonial|★/i)).not.toBeInTheDocument();
  });
});
