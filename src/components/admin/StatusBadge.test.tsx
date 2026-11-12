import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge, describeAdminAccountStatus } from "./StatusBadge";

// FVS-017-IMPLEMENTATION-PLAN.md T02 — generalized from a fixed
// "active"/"deactivated" union to a small, still-bounded `{label,
// tone}` descriptor, so the same component serves both admin-account
// status (FVS-009) and contact-message status (FVS-017) without
// becoming an untyped `{status: string; color: string}` component that
// would destroy its own type guarantees. `tone` stays a controlled,
// bounded union — never an arbitrary color string.

describe("StatusBadge", () => {
  // Phase 6E (axe color-contrast): warning text uses the AA `warning-text`
  // token, never the brand amber (#B8860B is ~3:1 on its own tint).
  it("renders warning text in the AA warning-text colour", () => {
    render(<StatusBadge label="Pending" tone="warning" />);
    expect(screen.getByText("Pending")).toHaveClass("text-warning-text");
    expect(screen.getByText("Pending")).not.toHaveClass("text-warning");
  });

  it("renders the supplied label as visible text", () => {
    render(<StatusBadge label="Archived" tone="neutral" />);
    expect(screen.getByText("Archived")).toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<StatusBadge label="Active" tone="positive" />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});

describe("describeAdminAccountStatus (FVS-009 regression)", () => {
  it("describes an active account", () => {
    expect(describeAdminAccountStatus("active")).toEqual({ label: "Active", tone: "positive" });
  });

  it("describes a deactivated account", () => {
    expect(describeAdminAccountStatus("deactivated")).toEqual({ label: "Deactivated", tone: "negative" });
  });

  it("still renders readable text for an active status end-to-end", () => {
    const { label, tone } = describeAdminAccountStatus("active");
    render(<StatusBadge label={label} tone={tone} />);
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("still renders readable text for a deactivated status end-to-end", () => {
    const { label, tone } = describeAdminAccountStatus("deactivated");
    render(<StatusBadge label={label} tone={tone} />);
    expect(screen.getByText("Deactivated")).toBeInTheDocument();
  });
});
