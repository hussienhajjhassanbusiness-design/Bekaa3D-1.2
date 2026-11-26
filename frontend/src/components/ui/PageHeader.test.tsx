import { describe, it, expect } from "vitest";
import { createRef } from "react";
import { render, screen } from "@testing-library/react";
import { PageHeader } from "./PageHeader";

// Redesign Batch 5 — layout-only page title block (COMPONENT-SPECS §64).

describe("PageHeader", () => {
  it("renders exactly one h1 with the eyebrow and description around it", () => {
    render(<PageHeader eyebrow="Account" title="Addresses" description="Saved delivery addresses." />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1, name: "Addresses" })).toBeInTheDocument();
    expect(screen.getByText("Account")).toBeInTheDocument();
    expect(screen.getByText("Saved delivery addresses.")).toBeInTheDocument();
  });

  it("renders actions when given and nothing extra when not", () => {
    const { rerender } = render(<PageHeader title="Profile" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    rerender(<PageHeader title="Profile" actions={<button type="button">Add address</button>} />);
    expect(screen.getByRole("button", { name: "Add address" })).toBeInTheDocument();
  });

  it("keeps meta in the same parent as the h1 (status read via heading → parent)", () => {
    render(<PageHeader title="Order 42" meta={<span>Paid</span>} />);
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading.parentElement).toHaveTextContent("Paid");
  });

  it("is a programmatic focus target only when the page passes a ref", () => {
    const { rerender } = render(<PageHeader title="Profile" />);
    expect(screen.getByRole("heading", { level: 1 })).not.toHaveAttribute("tabindex");
    const ref = createRef<HTMLHeadingElement>();
    rerender(<PageHeader title="Profile" headingRef={ref} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveAttribute("tabindex", "-1");
    expect(ref.current).toBe(screen.getByRole("heading", { level: 1 }));
  });
});
