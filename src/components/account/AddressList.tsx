"use client";

import { Button } from "@/components/forms/Button";
import { Alert } from "@/components/feedback/Alert";
import { EmptyState } from "@/components/feedback/EmptyState";
import { AddressCard } from "./AddressCard";
import type { AddressModel } from "@/lib/addresses/addressModel";

export interface AddressListProps {
  addresses: readonly AddressModel[];
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
  onAdd?: () => void;
  onEdit: (addressId: string) => void;
  onDelete: (addressId: string) => void;
  onSetDefault: (addressId: string) => void;
  pendingDefaultId?: string | null;
  actionsDisabled?: boolean;
}

const EMPTY_MESSAGE = "You have no saved addresses yet.";
const ERROR_MESSAGE = "We couldn't load your addresses. Please try again.";

// #FVS023-ADDRESS-LIST
//
// Presentational only — no network. Renders the server's order (default
// first) unchanged. Delete confirmation lives in the container
// (AddressBook) so it can stay open while the request is pending and
// close only on success.
// #SECURITY-CUSTOMER-ADDRESS — no address content is logged or stored.
export function AddressList({
  addresses,
  isLoading = false,
  isError = false,
  onRetry,
  onAdd,
  onEdit,
  onDelete,
  onSetDefault,
  pendingDefaultId = null,
  actionsDisabled = false,
}: AddressListProps) {
  if (isLoading) {
    return (
      <div role="status" className="grid grid-cols-1 gap-4 tablet:grid-cols-2">
        <span className="sr-only">Loading your addresses…</span>
        {[0, 1].map((index) => (
          <div
            key={index}
            aria-hidden="true"
            className="h-44 animate-pulse rounded-md bg-neutral-200 motion-reduce:animate-none"
          />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div>
        <Alert variant="error" message={ERROR_MESSAGE} />
        {onRetry && (
          <Button onClick={onRetry} className="mt-2">
            Retry
          </Button>
        )}
      </div>
    );
  }

  if (addresses.length === 0) {
    return <EmptyState message={EMPTY_MESSAGE} actionLabel={onAdd ? "Add an address" : undefined} onAction={onAdd} />;
  }

  return (
    <ul className="grid grid-cols-1 gap-4 tablet:grid-cols-2">
      {addresses.map((address) => (
        <li key={address.id}>
          <AddressCard
            address={address}
            onEdit={onEdit}
            onDelete={onDelete}
            onSetDefault={onSetDefault}
            isSettingDefault={pendingDefaultId === address.id}
            actionsDisabled={actionsDisabled || (pendingDefaultId !== null && pendingDefaultId !== address.id)}
          />
        </li>
      ))}
    </ul>
  );
}
