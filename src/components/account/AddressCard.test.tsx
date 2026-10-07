import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AddressCard } from "./AddressCard";
import type { AddressModel } from "@/lib/addresses/addressModel";

// FVS-023-IMPLEMENTATION-PLAN.md T02 — presentational only, no
// network, no query. `onEdit` is a seam: no `AddressForm` exists yet
// this batch (field matrix unconfirmed), so no caller supplies it and
// no dead Edit button renders. `onDelete` is always present — delete
// is fully safe to build presentationally this batch (the real
// network call is the caller's future job).

const ADDRESS: AddressModel = {
  id: "addr-1",
  displayLines: ["Jane Doe", "Main Street, Beirut"],
  isDefault: false,
};

const DEFAULT_ADDRESS: AddressModel = { ...ADDRESS, id: "addr-2", isDefault: true };

describe("AddressCard", () => {
  it("renders every display line", () => {
    render(<AddressCard address={ADDRESS} onDelete={vi.fn()} />);
    expect(screen.getByText("Jane Doe")).toBeInTheDocument();
    expect(screen.getByText("Main Street, Beirut")).toBeInTheDocument();
  });

  it("shows a visible 'Default' badge (text, not color-only) when the address is the default", () => {
    render(<AddressCard address={DEFAULT_ADDRESS} onDelete={vi.fn()} />);
    expect(screen.getByText("Default")).toBeInTheDocument();
  });

  it("shows no 'Default' badge for a non-default address", () => {
    render(<AddressCard address={ADDRESS} onDelete={vi.fn()} />);
    expect(screen.queryByText("Default")).not.toBeInTheDocument();
  });

  it("never renders shipping-zone or rate information", () => {
    render(<AddressCard address={DEFAULT_ADDRESS} onDelete={vi.fn()} />);
    expect(screen.queryByText(/zone/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/rate/i)).not.toBeInTheDocument();
  });

  it("renders no Edit button when onEdit is not supplied", () => {
    render(<AddressCard address={ADDRESS} onDelete={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /edit/i })).not.toBeInTheDocument();
  });

  it("renders a real Edit button that calls onEdit with the address id when supplied", async () => {
    const onEdit = vi.fn();
    const user = userEvent.setup();
    render(<AddressCard address={ADDRESS} onDelete={vi.fn()} onEdit={onEdit} />);

    await user.click(screen.getByRole("button", { name: /edit/i }));

    expect(onEdit).toHaveBeenCalledWith("addr-1");
  });

  it("always renders a Delete button that calls onDelete with the address id", async () => {
    const onDelete = vi.fn();
    const user = userEvent.setup();
    render(<AddressCard address={ADDRESS} onDelete={onDelete} />);

    await user.click(screen.getByRole("button", { name: /delete/i }));

    expect(onDelete).toHaveBeenCalledWith("addr-1");
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<AddressCard address={ADDRESS} onDelete={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
