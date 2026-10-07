import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge } from "./StatusBadge";

// FVS-009-IMPLEMENTATION-PLAN.md T02 — accepts a normalized frontend
// status union, never a claimed backend enum literal (plan §1/§5).
// Status must be conveyed in text, not color alone.

describe("StatusBadge", () => {
  it("shows readable text for an active status", () => {
    render(<StatusBadge status="active" />);
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("shows readable text for a deactivated status", () => {
    render(<StatusBadge status="deactivated" />);
    expect(screen.getByText("Deactivated")).toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<StatusBadge status="active" />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
