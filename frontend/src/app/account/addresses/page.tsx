import type { Metadata } from "next";
import { AddressBook } from "@/components/account/AddressBook";

// Phase 5B (FVS-023) — AccountLayout (mounted via src/app/account/
// layout.tsx) already supplies the ProtectedRoute boundary, the account
// nav and the content landmark; this server page only mounts the client
// address book, wired to the real /api/v1/me/addresses contract.
export const metadata: Metadata = {
  title: "Addresses — Bekaa3D",
};

export default function AccountAddressesPage() {
  return <AddressBook />;
}
