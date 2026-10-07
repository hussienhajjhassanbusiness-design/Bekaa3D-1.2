import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AddressList } from "./AddressList";
import type { AddressModel } from "@/lib/addresses/addressModel";

// FVS-023-IMPLEMENTATION-PLAN.md T02 (incl. T06 folded in) —
// presentational only, no network, no query. Delete confirmation is
// owned here (mirroring ReferenceDataManager's own inline
// ConfirmDialog/onArchive pattern) rather than a separate wrapper
// file. `onDelete` fires only after the user confirms, with the exact
// target id.

const ADDRESSES: AddressModel[] = [
  { id: "addr-1", displayLines: ["Jane Doe", "Main Street, Beirut"], isDefault: true },
  { id: "addr-2", displayLines: ["John Doe", "Second Street, Tripoli"], isDefault: false },
];

describe("AddressList", () => {
  it("shows a loading state", () => {
    render(<AddressList addresses={[]} isLoading onDelete={vi.fn()} />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("shows a safe error message with a retry action", async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    render(<AddressList addresses={[]} isError errorMessage="Couldn't load your addresses." onRetry={onRetry} onDelete={vi.fn()} />);

    expect(screen.getByText("Couldn't load your addresses.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("shows a safe empty-address-book message — no fake addresses", () => {
    render(<AddressList addresses={[]} onDelete={vi.fn()} />);
    expect(screen.getByText(/no saved addresses/i)).toBeInTheDocument();
  });

  it("renders every address's display lines", () => {
    render(<AddressList addresses={ADDRESSES} onDelete={vi.fn()} />);
    expect(screen.getByText("Jane Doe")).toBeInTheDocument();
    expect(screen.getByText("John Doe")).toBeInTheDocument();
  });

  it("indicates the default address as visible text", () => {
    render(<AddressList addresses={ADDRESSES} onDelete={vi.fn()} />);
    expect(screen.getByText("Default")).toBeInTheDocument();
  });

  it("never renders shipping-zone or rate information anywhere", () => {
    render(<AddressList addresses={ADDRESSES} onDelete={vi.fn()} />);
    expect(screen.queryByText(/zone/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/rate/i)).not.toBeInTheDocument();
  });

  it("opens a confirmation dialog before deleting, and calls onDelete with the exact target id only after confirming", async () => {
    const onDelete = vi.fn();
    const user = userEvent.setup();
    render(<AddressList addresses={ADDRESSES} onDelete={onDelete} />);

    await user.click(screen.getAllByRole("button", { name: /delete/i })[0]!);
    expect(onDelete).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Confirm" }));
    expect(onDelete).toHaveBeenCalledWith("addr-1");
  });

  it("does not call onDelete when the confirmation is cancelled", async () => {
    const onDelete = vi.fn();
    const user = userEvent.setup();
    render(<AddressList addresses={ADDRESSES} onDelete={onDelete} />);

    await user.click(screen.getAllByRole("button", { name: /delete/i })[0]!);
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onDelete).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<AddressList addresses={ADDRESSES} onDelete={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(<AddressList addresses={ADDRESSES} onDelete={vi.fn()} />);
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});
