import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { TextAreaField } from "./TextAreaField";

// Mirrors TextField's label/hint/error wiring for multi-line input.

describe("TextAreaField", () => {
  it("is a textarea labelled by its label", () => {
    render(<TextAreaField label="Landmark notes" />);
    const textarea = screen.getByLabelText("Landmark notes");
    expect(textarea.tagName).toBe("TEXTAREA");
  });

  it("links hint and error through aria-describedby and marks itself invalid on error", () => {
    render(<TextAreaField label="Notes" hint="Nearby landmarks" error="Add notes." />);
    const textarea = screen.getByLabelText("Notes");
    expect(textarea).toHaveAttribute("aria-invalid", "true");
    expect(textarea).toHaveAccessibleDescription("Nearby landmarks Add notes.");
  });

  it("is not marked invalid without an error", () => {
    render(<TextAreaField label="Notes" />);
    expect(screen.getByLabelText("Notes")).not.toHaveAttribute("aria-invalid");
  });
});
