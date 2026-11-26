import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusTimeline } from "./StatusTimeline";

// FVS-029-IMPLEMENTATION-PLAN.md T04 — fully caller-supplied; never
// encodes a fulfillment state machine itself, never invents
// paid/production/printing/delivery/delivered as a canonical graph.

describe("StatusTimeline", () => {
  it("renders every supplied entry's label in order", () => {
    render(
      <StatusTimeline
        entries={[
          { label: "Order placed" },
          { label: "Shipped" },
          { label: "Delivered" },
        ]}
      />
    );
    const items = screen.getAllByRole("listitem");
    expect(items.map((el) => el.textContent)).toEqual([
      expect.stringContaining("Order placed"),
      expect.stringContaining("Shipped"),
      expect.stringContaining("Delivered"),
    ]);
  });

  it("renders an entry's timeLabel when supplied", () => {
    render(<StatusTimeline entries={[{ label: "Shipped", timeLabel: "Oct 5, 2026" }]} />);
    expect(screen.getByText("Oct 5, 2026")).toBeInTheDocument();
  });

  it("conveys current/completed state via visible text, not color alone", () => {
    render(<StatusTimeline entries={[{ label: "Shipped", isCurrent: true }, { label: "Order placed", isCompleted: true }]} />);
    expect(screen.getByText(/current/i)).toBeInTheDocument();
    expect(screen.getByText(/completed/i)).toBeInTheDocument();
  });

  it("renders gracefully with zero entries — no crash", () => {
    render(<StatusTimeline entries={[]} />);
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });

  it("hardcodes no fulfillment status literal anywhere", () => {
    render(<StatusTimeline entries={[{ label: "Custom Stage" }]} />);
    expect(screen.queryByText(/production|printing|out for delivery/i)).not.toBeInTheDocument();
  });
});
