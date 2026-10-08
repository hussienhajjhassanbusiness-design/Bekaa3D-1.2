import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DeliveryMethodSelector } from "./DeliveryMethodSelector";
import type { AddressModel } from "@/lib/addresses/addressModel";
import type { ShippingZoneOption } from "@/lib/shippingZones/shippingZoneModels";

// FVS-026-IMPLEMENTATION-PLAN.md T04 — reuses FVS-023's AddressModel
// and FVS-024's ShippingZoneOption directly, no checkout-specific
// duplicate. No address-to-zone inference: selecting an address never
// pre-fills a zone. Pickup renders only when pickupAvailable is true
// — no invented default availability.

const ADDRESSES: readonly AddressModel[] = [
  { id: "addr-1", displayLines: ["Jane Doe", "Main Street, Beirut"], isDefault: true },
  { id: "addr-2", displayLines: ["John Doe", "Second Street, Tripoli"], isDefault: false },
];

const ZONES: readonly ShippingZoneOption[] = [
  { id: "zone-1", displayName: "Beirut", rateCents: 50000, currency: "USD" },
  { id: "zone-2", displayName: "Tripoli", rateCents: 70000, currency: "USD" },
];

describe("DeliveryMethodSelector", () => {
  it("renders one radio per saved address", () => {
    render(<DeliveryMethodSelector addresses={ADDRESSES} zones={ZONES} selection={null} onSelect={vi.fn()} />);
    expect(screen.getAllByRole("radio")).toHaveLength(2);
  });

  it("renders a Pickup option only when pickupAvailable is true", () => {
    render(<DeliveryMethodSelector addresses={ADDRESSES} zones={ZONES} selection={null} onSelect={vi.fn()} pickupAvailable />);
    expect(screen.getByRole("radio", { name: /pickup/i })).toBeInTheDocument();
  });

  it("omits Pickup entirely when pickupAvailable is not supplied — no invented default", () => {
    render(<DeliveryMethodSelector addresses={ADDRESSES} zones={ZONES} selection={null} onSelect={vi.fn()} />);
    expect(screen.queryByRole("radio", { name: /pickup/i })).not.toBeInTheDocument();
  });

  it("choosing an address does not call onSelect with any zone pre-filled", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<DeliveryMethodSelector addresses={ADDRESSES} zones={ZONES} selection={null} onSelect={onSelect} />);

    await user.click(screen.getByRole("radio", { name: /jane doe/i }));

    expect(onSelect).not.toHaveBeenCalled();
  });

  it("choosing a zone for the selected address calls onSelect with the complete selection", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<DeliveryMethodSelector addresses={ADDRESSES} zones={ZONES} selection={null} onSelect={onSelect} />);

    await user.click(screen.getByRole("radio", { name: /jane doe/i }));
    await user.selectOptions(screen.getByRole("combobox", { name: /shipping zone/i }), "zone-1");

    expect(onSelect).toHaveBeenCalledWith({ kind: "address", addressId: "addr-1", zoneId: "zone-1" });
  });

  it("choosing Pickup calls onSelect with a pickup selection immediately", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<DeliveryMethodSelector addresses={ADDRESSES} zones={ZONES} selection={null} onSelect={onSelect} pickupAvailable />);

    await user.click(screen.getByRole("radio", { name: /pickup/i }));

    expect(onSelect).toHaveBeenCalledWith({ kind: "pickup" });
  });

  it("contains no governorate/address-parsing logic — the zone select is always a plain, explicit control", () => {
    const { container } = render(<DeliveryMethodSelector addresses={ADDRESSES} zones={ZONES} selection={null} onSelect={vi.fn()} />);
    expect(container.textContent).not.toMatch(/governorate/i);
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<DeliveryMethodSelector addresses={ADDRESSES} zones={ZONES} selection={null} onSelect={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
