import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ProductTypeBadge } from "./ProductTypeBadge";

// FVS-014-IMPLEMENTATION-PLAN.md T02 — "physical"/"stl" are internal
// frontend UI literals (mirroring FVS-011's ProductTypeSelector
// vocabulary without importing that admin-scoped module), never a claim
// about the backend's real discriminator field/enum strings. Type is
// communicated through visible text, never icon/color alone.

describe("ProductTypeBadge", () => {
  it("shows readable text for a physical product", () => {
    render(<ProductTypeBadge type="physical" />);
    expect(screen.getByText("Physical")).toBeInTheDocument();
  });

  it("shows readable text for an STL product", () => {
    render(<ProductTypeBadge type="stl" />);
    expect(screen.getByText("STL")).toBeInTheDocument();
  });
});
