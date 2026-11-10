import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DeliveryMethodSelector } from "./DeliveryMethodSelector";
import type { AddressModel } from "@/lib/addresses/addressModel";

// Phase 5B — the real AddressModel fields; only id/displayLines/isDefault
// matter to these tests.
const ADDRESS_BASE: Omit<AddressModel, "id" | "displayLines" | "isDefault"> = {
  label: "Home",
  recipientName: "Jane Doe",
  phone: "+9613123456",
  governorate: "beirut",
  city: "Beirut",
  area: null,
  street: null,
  landmarkNotes: "Blue gate",
};

// FVS-026-IMPLEMENTATION-PLAN.md T04 — reuses FVS-023's AddressModel
// directly, no checkout-specific duplicate. ADR-024 removed shipping
// charges, so there is no zone step: choosing an address is itself a
// complete selection, fired immediately. Pickup renders only when
// pickupAvailable is true — no invented default availability.

const ADDRESSES: readonly AddressModel[] = [
  { ...ADDRESS_BASE, id: "addr-1", displayLines: ["Jane Doe", "Main Street, Beirut"], isDefault: true },
  { ...ADDRESS_BASE, id: "addr-2", displayLines: ["John Doe", "Second Street, Tripoli"], isDefault: false },
];

describe("DeliveryMethodSelector", () => {
  it("renders one radio per saved address", () => {
    render(<DeliveryMethodSelector addresses={ADDRESSES} selection={null} onSelect={vi.fn()} />);
    expect(screen.getAllByRole("radio")).toHaveLength(2);
  });

  it("renders a Pickup option only when pickupAvailable is true", () => {
    render(<DeliveryMethodSelector addresses={ADDRESSES} selection={null} onSelect={vi.fn()} pickupAvailable />);
    expect(screen.getByRole("radio", { name: /pickup/i })).toBeInTheDocument();
  });

  it("omits Pickup entirely when pickupAvailable is not supplied — no invented default", () => {
    render(<DeliveryMethodSelector addresses={ADDRESSES} selection={null} onSelect={vi.fn()} />);
    expect(screen.queryByRole("radio", { name: /pickup/i })).not.toBeInTheDocument();
  });

  it("choosing an address calls onSelect with a complete selection immediately — no shipping-zone step", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<DeliveryMethodSelector addresses={ADDRESSES} selection={null} onSelect={onSelect} />);

    await user.click(screen.getByRole("radio", { name: /jane doe/i }));

    expect(onSelect).toHaveBeenCalledWith({ kind: "address", addressId: "addr-1" });
  });

  it("choosing Pickup calls onSelect with a pickup selection immediately", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<DeliveryMethodSelector addresses={ADDRESSES} selection={null} onSelect={onSelect} pickupAvailable />);

    await user.click(screen.getByRole("radio", { name: /pickup/i }));

    expect(onSelect).toHaveBeenCalledWith({ kind: "pickup" });
  });

  it("switching to a different address calls onSelect with the new address, not a stale/null intermediate", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(
      <DeliveryMethodSelector
        addresses={ADDRESSES}
        selection={{ kind: "address", addressId: "addr-1" }}
        onSelect={onSelect}
      />
    );

    await user.click(screen.getByRole("radio", { name: /john doe/i }));

    expect(onSelect).toHaveBeenCalledWith({ kind: "address", addressId: "addr-2" });
  });

  it("marks the address matching the current selection as checked", () => {
    render(
      <DeliveryMethodSelector
        addresses={ADDRESSES}
        selection={{ kind: "address", addressId: "addr-1" }}
        onSelect={vi.fn()}
      />
    );
    expect(screen.getByRole("radio", { name: /jane doe/i })).toBeChecked();
  });

  it("contains no governorate/address-parsing logic or shipping-zone control", () => {
    const { container } = render(<DeliveryMethodSelector addresses={ADDRESSES} selection={null} onSelect={vi.fn()} />);
    expect(container.textContent).not.toMatch(/governorate|shipping zone/i);
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<DeliveryMethodSelector addresses={ADDRESSES} selection={null} onSelect={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
