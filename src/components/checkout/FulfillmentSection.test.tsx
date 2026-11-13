import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FulfillmentSection, type FulfillmentSectionProps } from "./FulfillmentSection";
import type { AddressModel } from "@/lib/addresses/addressModel";

// Delivery (saved address, no contact phone) vs pickup (contact phone, no
// address), exactly as backend 2dfb27b domain/fulfillment.py. Pickup only
// when public settings carry a pickup address. ADR-024: no zone, no fee.

const ADDRESS: AddressModel = {
  id: "a-1",
  label: "Home",
  recipientName: "Ada",
  phone: "+96170123456",
  governorate: "beqaa",
  city: "Zahle",
  area: null,
  street: "Main St",
  landmarkNotes: "Blue door",
  isDefault: true,
  displayLines: ["Ada", "Main St", "Zahle, Beqaa", "+96170123456"],
};

function props(overrides: Partial<FulfillmentSectionProps> = {}): FulfillmentSectionProps {
  return {
    value: null,
    onChange: vi.fn(),
    addresses: [ADDRESS],
    addressesLoading: false,
    addressesError: false,
    onRetryAddresses: vi.fn(),
    addressId: null,
    onAddressChange: vi.fn(),
    contactPhone: "",
    onContactPhoneChange: vi.fn(),
    pickup: {
      available: true,
      address: "Bekaa3D workshop, Zahle",
      hours: "Mon-Fri 10-18",
    },
    errors: {},
    ...overrides,
  };
}

describe("FulfillmentSection", () => {
  it("offers delivery and pickup, and nothing about zones or shipping cost", () => {
    render(<FulfillmentSection {...props()} />);
    expect(screen.getByRole("radio", { name: /Delivery/ })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Pickup/ })).toBeInTheDocument();
    expect(screen.queryByText(/zone/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/free shipping/i)).not.toBeInTheDocument();
  });

  it("hides pickup when the shop has no pickup address", () => {
    render(<FulfillmentSection {...props({ pickup: { available: false, address: null, hours: null } })} />);
    expect(screen.queryByRole("radio", { name: /Pickup/ })).not.toBeInTheDocument();
  });

  it("delivery: lists saved addresses, links to the address book, and explains the courier fee", async () => {
    const onAddressChange = vi.fn();
    render(<FulfillmentSection {...props({ value: "delivery", onAddressChange })} />);
    await userEvent.click(screen.getByRole("radio", { name: /Home/ }));
    expect(onAddressChange).toHaveBeenCalledWith("a-1");
    expect(screen.getByRole("link", { name: "Manage addresses" })).toHaveAttribute("href", "/account/addresses");
    expect(screen.getByText(/pay it to them directly on delivery/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Contact phone")).not.toBeInTheDocument();
  });

  it("delivery with no saved address sends the customer to the address book", () => {
    render(<FulfillmentSection {...props({ value: "delivery", addresses: [] })} />);
    expect(screen.getByRole("link", { name: "Add an address" })).toHaveAttribute("href", "/account/addresses");
  });

  it("pickup: shows the configured pickup address and hours and asks for a contact phone", async () => {
    const onContactPhoneChange = vi.fn();
    render(<FulfillmentSection {...props({ value: "pickup", onContactPhoneChange })} />);
    expect(screen.getByText("Bekaa3D workshop, Zahle")).toBeInTheDocument();
    expect(screen.getByText("Mon-Fri 10-18")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Contact phone"), "7");
    expect(onContactPhoneChange).toHaveBeenCalledWith("7");
    expect(screen.queryByRole("radio", { name: /Home/ })).not.toBeInTheDocument();
  });

  it("shows field errors and an address-load failure with a retry", async () => {
    const onRetryAddresses = vi.fn();
    const { rerender } = render(
      <FulfillmentSection
        {...props({
          value: "pickup",
          errors: { contactPhone: "Enter a valid Lebanese phone number." },
        })}
      />
    );
    expect(screen.getByLabelText("Contact phone")).toHaveAccessibleDescription(/Enter a valid Lebanese phone number\./);
    rerender(
      <FulfillmentSection
        {...props({
          value: "delivery",
          addressesError: true,
          onRetryAddresses,
        })}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetryAddresses).toHaveBeenCalled();
  });

  // Redesign Batch 6.
  it("the step heading is an h2 that names the method group", () => {
    render(<FulfillmentSection {...props()} />);
    expect(screen.getByRole("heading", { level: 2, name: "Delivery or pickup" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Delivery or pickup" })).toBeInTheDocument();
  });

  it("delivery: the address group is labelled and the default address says so in text", () => {
    render(<FulfillmentSection {...props({ value: "delivery" })} />);
    const group = screen.getByRole("group", { name: "Delivery address" });
    expect(group).toHaveTextContent("Default");
  });

  it("pickup only shows pickup details; delivery only shows addresses", () => {
    const { rerender } = render(<FulfillmentSection {...props({ value: "pickup" })} />);
    expect(screen.queryByRole("group", { name: "Delivery address" })).not.toBeInTheDocument();
    rerender(<FulfillmentSection {...props({ value: "delivery" })} />);
    expect(screen.queryByLabelText("Contact phone")).not.toBeInTheDocument();
    expect(screen.queryByText("Pickup location")).not.toBeInTheDocument();
  });

  it("disabled while submitting: every choice is locked", () => {
    render(<FulfillmentSection {...props({ value: "delivery", disabled: true })} />);
    for (const radio of screen.getAllByRole("radio")) {
      expect(radio).toBeDisabled();
    }
  });
});
