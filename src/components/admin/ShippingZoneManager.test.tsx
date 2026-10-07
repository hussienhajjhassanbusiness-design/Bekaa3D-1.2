import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ShippingZoneManager } from "./ShippingZoneManager";
import type { ShippingZoneAdminModel } from "@/lib/shippingZones/shippingZoneModels";

// FVS-024-IMPLEMENTATION-PLAN.md T03 (T02/T04 folded in) —
// presentational only (no fetch, no TanStack Query, no production
// mutation, no shipping-price/zone-matching computation). A focused
// component, not a forced ReferenceDataManager extension (money
// doesn't fit its string-only draft shape) — but reuses the exact
// same responsive stacked-card / inline-form / ConfirmDialog-archive
// pattern. Rate editing reuses MoneyInput directly (no separate field
// wrapper); rate display reuses PriceDisplay (no duplicated currency
// formatting).

function makeZone(overrides: Partial<ShippingZoneAdminModel> = {}): ShippingZoneAdminModel {
  return { id: "zone-1", displayName: "Beirut", rateCents: 50000, currency: "USD", isArchived: false, ...overrides };
}

describe("ShippingZoneManager", () => {
  it("shows the configured empty-state message when there are no zones", () => {
    render(<ShippingZoneManager zones={[]} currency="USD" onSave={vi.fn()} onArchive={vi.fn()} />);
    expect(screen.getByText(/no shipping zones yet/i)).toBeInTheDocument();
  });

  it("renders a zone's display name", () => {
    render(<ShippingZoneManager zones={[makeZone()]} currency="USD" onSave={vi.fn()} onArchive={vi.fn()} />);
    expect(screen.getByText("Beirut")).toBeInTheDocument();
  });

  it("renders a zone's rate via PriceDisplay, using the exact supplied currency", () => {
    render(<ShippingZoneManager zones={[makeZone({ rateCents: 150000 })]} currency="USD" onSave={vi.fn()} onArchive={vi.fn()} />);
    expect(screen.getByText("$1,500.00")).toBeInTheDocument();
  });

  it("shows archived state as visible text, not color alone", () => {
    render(<ShippingZoneManager zones={[makeZone({ isArchived: true })]} currency="USD" onSave={vi.fn()} onArchive={vi.fn()} />);
    expect(screen.getByText(/archived/i)).toBeInTheDocument();
  });

  it("disables further archiving for an already-archived zone", () => {
    render(<ShippingZoneManager zones={[makeZone({ isArchived: true })]} currency="USD" onSave={vi.fn()} onArchive={vi.fn()} />);
    expect(screen.getByRole("button", { name: /archive/i })).toBeDisabled();
  });

  it("uses a responsive stacked-card row structure, not a horizontal-scroll table", () => {
    render(<ShippingZoneManager zones={[makeZone()]} currency="USD" onSave={vi.fn()} onArchive={vi.fn()} />);
    const row = screen.getByText("Beirut").closest("li");
    expect(row?.className).toMatch(/flex-col/);
    expect(row?.className).toMatch(/tablet:flex-row/);
  });

  it("opens a create form using MoneyInput for the rate field", async () => {
    const user = userEvent.setup();
    render(<ShippingZoneManager zones={[]} currency="USD" onSave={vi.fn()} onArchive={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /add zone/i }));

    expect(screen.getByLabelText("Name")).toHaveValue("");
    expect(screen.getByLabelText(/rate \(usd\)/i)).toBeInTheDocument();
  });

  it("opens an edit form pre-filled with the zone's name and cents-accurate rate", async () => {
    const user = userEvent.setup();
    render(<ShippingZoneManager zones={[makeZone({ rateCents: 1234 })]} currency="USD" onSave={vi.fn()} onArchive={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /edit/i }));

    expect(screen.getByLabelText("Name")).toHaveValue("Beirut");
    expect(screen.getByLabelText(/rate \(usd\)/i)).toHaveValue("12.34");
  });

  it("Save calls onSave with the typed name and exact cents value for a new zone", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(<ShippingZoneManager zones={[]} currency="USD" onSave={onSave} onArchive={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /add zone/i }));
    await user.type(screen.getByLabelText("Name"), "Tripoli");
    await user.type(screen.getByLabelText(/rate \(usd\)/i), "25.50");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    expect(onSave).toHaveBeenCalledWith({ displayName: "Tripoli", rateCents: 2550 }, null);
  });

  it("accepts a zero rate — a free-shipping zone — with no invented minimum", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(<ShippingZoneManager zones={[]} currency="USD" onSave={onSave} onArchive={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /add zone/i }));
    await user.type(screen.getByLabelText("Name"), "Pickup");
    await user.type(screen.getByLabelText(/rate \(usd\)/i), "0.00");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    expect(onSave).toHaveBeenCalledWith({ displayName: "Pickup", rateCents: 0 }, null);
  });

  it("Save calls onSave with the editing zone's id when editing", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(<ShippingZoneManager zones={[makeZone({ id: "zone-9" })]} currency="USD" onSave={onSave} onArchive={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /edit/i }));
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ displayName: "Beirut" }), "zone-9");
  });

  it("never performs floating-point money conversion — never parseFloat(text) * 100", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(<ShippingZoneManager zones={[]} currency="USD" onSave={onSave} onArchive={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /add zone/i }));
    await user.type(screen.getByLabelText("Name"), "Rounding Check");
    await user.type(screen.getByLabelText(/rate \(usd\)/i), "0.10");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    // parseFloat("0.10") * 100 can produce 9.999999999999998 in plain
    // JS float math; MoneyInput's string-based parser must never do
    // that — the saved value must be exactly 10 cents.
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ rateCents: 10 }), null);
  });

  it("submits a null rate without a client-side guard — deliberately deferred to server validation, not an oversight", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(<ShippingZoneManager zones={[]} currency="USD" onSave={onSave} onArchive={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /add zone/i }));
    await user.type(screen.getByLabelText("Name"), "No Rate Yet");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    expect(onSave).toHaveBeenCalledWith({ displayName: "No Rate Yet", rateCents: null }, null);
  });

  it("disables Save while isSaving, preventing a duplicate submit", async () => {
    const user = userEvent.setup();
    render(<ShippingZoneManager zones={[]} currency="USD" onSave={vi.fn()} onArchive={vi.fn()} isSaving />);

    await user.click(screen.getByRole("button", { name: /add zone/i }));

    expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();
  });

  it("shows an inline, normalized field error next to the Name field", async () => {
    const user = userEvent.setup();
    render(
      <ShippingZoneManager
        zones={[]}
        currency="USD"
        onSave={vi.fn()}
        onArchive={vi.fn()}
        fieldErrors={{ displayName: "This name is already in use." }}
      />
    );

    await user.click(screen.getByRole("button", { name: /add zone/i }));

    expect(screen.getByText("This name is already in use.")).toBeInTheDocument();
  });

  it("clicking Archive opens the shared ConfirmDialog, not a new modal", async () => {
    const user = userEvent.setup();
    render(<ShippingZoneManager zones={[makeZone()]} currency="USD" onSave={vi.fn()} onArchive={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /archive/i }));

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByText(/archive shipping zone/i)).toBeInTheDocument();
  });

  it("Cancel in the archive dialog closes it without calling onArchive", async () => {
    const onArchive = vi.fn();
    const user = userEvent.setup();
    render(<ShippingZoneManager zones={[makeZone()]} currency="USD" onSave={vi.fn()} onArchive={onArchive} />);

    await user.click(screen.getByRole("button", { name: /archive/i }));
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(onArchive).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("Confirm in the archive dialog calls onArchive with the exact zone id", async () => {
    const onArchive = vi.fn();
    const user = userEvent.setup();
    render(<ShippingZoneManager zones={[makeZone({ id: "zone-7" })]} currency="USD" onSave={vi.fn()} onArchive={onArchive} />);

    await user.click(screen.getByRole("button", { name: /archive/i }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /^archive$/i }));

    expect(onArchive).toHaveBeenCalledWith("zone-7");
  });

  it("never renders a 'Delete' button — archive, never hard delete, is this product's semantics", () => {
    render(<ShippingZoneManager zones={[makeZone()]} currency="USD" onSave={vi.fn()} onArchive={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<ShippingZoneManager zones={[makeZone()]} currency="USD" onSave={vi.fn()} onArchive={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(<ShippingZoneManager zones={[makeZone()]} currency="USD" onSave={vi.fn()} onArchive={vi.fn()} />);
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});
