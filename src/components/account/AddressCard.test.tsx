import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AddressCard } from "./AddressCard";
import { adaptAddress } from "@/lib/addresses/addressModel";
import type { AddressReadDTO } from "@/lib/addresses/addressTypes";

// Phase 5B — presentational card for one real AddressRead. No network.

const DTO: AddressReadDTO = {
  id: "addr-1",
  label: "Home",
  recipient_name: "Jane Doe",
  phone: "+9613123456",
  governorate: "mount_lebanon",
  city: "Jounieh",
  area: "Kaslik",
  street: "Main Street",
  landmark_notes: "Blue gate next to the bakery",
  is_default: false,
  created_at: "2026-11-01T10:00:00Z",
  updated_at: "2026-11-01T10:00:00Z",
};

const ADDRESS = adaptAddress(DTO);
const DEFAULT_ADDRESS = adaptAddress({ ...DTO, id: "addr-2", is_default: true });

function renderCard(overrides: Partial<Parameters<typeof AddressCard>[0]> = {}) {
  const props = { address: ADDRESS, onEdit: vi.fn(), onDelete: vi.fn(), onSetDefault: vi.fn(), ...overrides };
  render(<AddressCard {...props} />);
  return props;
}

describe("AddressCard", () => {
  it("shows the label as a heading and every address part, including landmark notes", () => {
    renderCard();
    expect(screen.getByRole("heading", { name: "Home" })).toBeInTheDocument();
    expect(screen.getByText("Jane Doe")).toBeInTheDocument();
    expect(screen.getByText("Main Street, Kaslik")).toBeInTheDocument();
    expect(screen.getByText("Jounieh, Mount Lebanon")).toBeInTheDocument();
    expect(screen.getByText("+9613123456")).toBeInTheDocument();
    expect(screen.getByText("Blue gate next to the bakery")).toBeInTheDocument();
  });

  it("shows a visible 'Default' text badge only for the default address", () => {
    renderCard({ address: DEFAULT_ADDRESS });
    expect(screen.getByText("Default")).toBeInTheDocument();
  });

  it("offers 'Set as default' only for a non-default address, and reports the id", async () => {
    const user = userEvent.setup();
    const props = renderCard();
    await user.click(screen.getByRole("button", { name: "Set as default: Home" }));
    expect(props.onSetDefault).toHaveBeenCalledWith("addr-1");
  });

  it("shows no 'Set as default' action on the current default", () => {
    renderCard({ address: DEFAULT_ADDRESS });
    expect(screen.queryByRole("button", { name: /set as default/i })).not.toBeInTheDocument();
  });

  it("Edit and Delete report the id, with accessible names that include the label", async () => {
    const user = userEvent.setup();
    const props = renderCard();
    await user.click(screen.getByRole("button", { name: "Edit Home" }));
    await user.click(screen.getByRole("button", { name: "Delete Home" }));
    expect(props.onEdit).toHaveBeenCalledWith("addr-1");
    expect(props.onDelete).toHaveBeenCalledWith("addr-1");
  });

  it("while its default switch is pending, the button shows a busy state", () => {
    renderCard({ isSettingDefault: true });
    expect(screen.getByRole("button", { name: "Set as default: Home" })).toHaveAttribute("aria-busy", "true");
  });

  it("actionsDisabled disables every action", () => {
    renderCard({ actionsDisabled: true });
    for (const button of within(screen.getByRole("article")).getAllByRole("button")) {
      expect(button).toBeDisabled();
    }
  });

  it("never renders shipping-zone, rate or fee information (ADR-024)", () => {
    renderCard({ address: DEFAULT_ADDRESS });
    expect(screen.queryByText(/zone|shipping|fee/i)).not.toBeInTheDocument();
  });

  it("labels recipient, phone, location and landmark notes as term/definition pairs (Batch 5)", () => {
    renderCard();
    const card = screen.getByRole("article", { name: "Home" });
    for (const term of ["Recipient", "Phone", "Location", "Landmark notes"]) {
      expect(within(card).getByText(term).tagName).toBe("DT");
    }
    expect(within(card).getByText("+9613123456").closest("dd")).not.toBeNull();
  });

  it("communicates the default state as text, and the card is not itself a control", () => {
    renderCard({ address: DEFAULT_ADDRESS });
    const card = screen.getByRole("article", { name: "Home" });
    expect(within(card).getByText("Default")).toBeVisible();
    expect(card).not.toHaveAttribute("role", "button");
    expect(card.closest("a, button")).toBeNull();
    expect(within(card).getAllByRole("button").map((button) => button.getAttribute("aria-label"))).toEqual([
      "Edit Home",
      "Delete Home",
    ]);
  });
});
