import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { UnavailableNotice } from "./UnavailableNotice";

// FVS-014-IMPLEMENTATION-PLAN.md T02 — presentational only. Receives
// its copy/state from the parent; never infers availability from
// missing fields and never encodes a backend status literal itself.
// Carries no purchase action — a WhatsApp CTA, if applicable, is a
// sibling the parent renders separately.

describe("UnavailableNotice", () => {
  it("renders the supplied message", () => {
    render(<UnavailableNotice message="This product is currently unavailable." />);
    expect(screen.getByText("This product is currently unavailable.")).toBeInTheDocument();
  });

  it("renders no purchase action of its own", () => {
    render(<UnavailableNotice message="This product is currently unavailable." />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
