import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import AccountAddressesPage, { metadata } from "./page";

// /account/addresses — the AccountLayout route layout (src/app/account/
// layout.tsx) supplies the ProtectedRoute boundary and nav; the page only
// mounts the address book.
vi.mock("@/components/account/AddressBook", () => ({
  AddressBook: () => <div data-testid="address-book" />,
}));

describe("AccountAddressesPage (/account/addresses)", () => {
  it("mounts the address book", () => {
    render(<AccountAddressesPage />);
    expect(screen.getByTestId("address-book")).toBeInTheDocument();
  });

  it("has a page title", () => {
    expect(metadata.title).toMatch(/addresses/i);
  });
});
