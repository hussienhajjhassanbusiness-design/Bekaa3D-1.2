import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AddressList } from "./AddressList";
import { adaptAddress } from "@/lib/addresses/addressModel";
import type { AddressReadDTO } from "@/lib/addresses/addressTypes";

// Phase 5B — presentational list; the container (AddressBook) owns the
// delete confirmation so it can stay open while the request is pending.

const BASE: AddressReadDTO = {
  id: "addr-1",
  label: "Home",
  recipient_name: "Jane Doe",
  phone: "+9613123456",
  governorate: "beirut",
  city: "Beirut",
  area: null,
  street: "Bliss Street",
  landmark_notes: "Blue gate",
  is_default: true,
  created_at: "2026-11-01T10:00:00Z",
  updated_at: "2026-11-01T10:00:00Z",
};

const ADDRESSES = [
  adaptAddress(BASE),
  adaptAddress({ ...BASE, id: "addr-2", label: "Work", recipient_name: "John Doe", is_default: false }),
];

function props(overrides: Partial<Parameters<typeof AddressList>[0]> = {}) {
  return { addresses: ADDRESSES, onEdit: vi.fn(), onDelete: vi.fn(), onSetDefault: vi.fn(), ...overrides };
}

describe("AddressList", () => {
  it("shows a loading state", () => {
    render(<AddressList {...props({ addresses: [], isLoading: true })} />);
    expect(screen.getByRole("status")).toHaveTextContent(/loading your addresses/i);
  });

  it("shows a safe error message with a retry action", async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    render(<AddressList {...props({ addresses: [], isError: true, onRetry })} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/couldn't load your addresses/i);
    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("shows an empty state with an add action when there are no addresses", async () => {
    const onAdd = vi.fn();
    const user = userEvent.setup();
    render(<AddressList {...props({ addresses: [], onAdd })} />);
    expect(screen.getByText(/no saved addresses/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /add an address/i }));
    expect(onAdd).toHaveBeenCalledTimes(1);
  });

  it("renders one list item per address, in the server's order", () => {
    render(<AddressList {...props()} />);
    const headings = screen.getAllByRole("heading").map((heading) => heading.textContent);
    expect(headings).toEqual(["Home", "Work"]);
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("forwards delete requests with the id (no confirmation here — the container owns it)", async () => {
    const user = userEvent.setup();
    const p = props();
    render(<AddressList {...p} />);
    await user.click(screen.getByRole("button", { name: "Delete Work" }));
    expect(p.onDelete).toHaveBeenCalledWith("addr-2");
  });

  it("marks only the pending card's default button busy", () => {
    render(<AddressList {...props({ pendingDefaultId: "addr-2" })} />);
    expect(screen.getByRole("button", { name: "Set as default: Work" })).toHaveAttribute("aria-busy", "true");
  });
});
