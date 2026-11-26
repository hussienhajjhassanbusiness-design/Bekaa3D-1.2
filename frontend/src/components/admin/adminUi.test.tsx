import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { AdminBackLink, AdminField, AdminRow, AdminSection } from "./adminUi";

// Redesign Batch 10 — the shared admin detail building blocks are
// presentation only: a section named by its visible h2, label/value rows and
// stacked facts as real <dl> content, and a back link.

describe("adminUi", () => {
  it("names a section region by its visible h2 and renders the optional description", () => {
    render(
      <AdminSection title="Payment" description="Server amounts only.">
        <p>body</p>
      </AdminSection>
    );
    const region = screen.getByRole("region", { name: "Payment" });
    expect(region).toContainElement(screen.getByRole("heading", { level: 2, name: "Payment" }));
    expect(region).toHaveTextContent("Server amounts only.");
  });

  it("sets financial sections apart with the danger tone (still a named region, status in text)", () => {
    render(
      <AdminSection title="Refund actions" tone="danger">
        <button type="button">Settle</button>
      </AdminSection>
    );
    const region = screen.getByRole("region", { name: "Refund actions" });
    expect(region.className).toMatch(/border-t-error/);
  });

  it("renders rows and fields as description terms and details", () => {
    render(
      <dl>
        <AdminRow label="Total">$36.00</AdminRow>
        <AdminRow label="Reference" breakAll>
          REF-123
        </AdminRow>
        <AdminField label="From">Rana</AdminField>
      </dl>
    );
    expect(screen.getAllByRole("term").map((t) => t.textContent)).toEqual(["Total", "Reference", "From"]);
    expect(screen.getAllByRole("definition").map((d) => d.textContent)).toEqual(["$36.00", "REF-123", "Rana"]);
    expect(screen.getByText("REF-123").className).toMatch(/break-all/);
  });

  it("renders the back link as a real link", () => {
    render(<AdminBackLink href="/admin/orders">Back to orders</AdminBackLink>);
    expect(screen.getByRole("link", { name: "Back to orders" })).toHaveAttribute("href", "/admin/orders");
  });
});
