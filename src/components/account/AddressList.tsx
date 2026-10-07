"use client";

import { useState } from "react";
import { Button } from "@/components/forms/Button";
import { Alert } from "@/components/feedback/Alert";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { AddressCard } from "./AddressCard";
import type { AddressModel } from "@/lib/addresses/addressModel";

export interface AddressListProps {
  addresses: readonly AddressModel[];
  isLoading?: boolean;
  isError?: boolean;
  errorMessage?: string;
  onRetry?: () => void;
  onDelete: (addressId: string) => void;
  onEdit?: (addressId: string) => void;
}

const EMPTY_MESSAGE = "You have no saved addresses yet.";
const DEFAULT_ERROR_MESSAGE = "We couldn't load your addresses. Please try again.";

// #FVS023-ADDRESS-LIST
//
// Presentational only — no network, no query. Delete confirmation is
// owned here, mirroring ReferenceDataManager's own inline
// ConfirmDialog/onArchive pattern, rather than a separate wrapper
// component (plan §2, T06 folded in). `onDelete` fires only after the
// user confirms, with the exact target id — never eagerly on click.
// #SECURITY-CUSTOMER-ADDRESS — no address content is logged, stored,
// or sent anywhere by this component.
export function AddressList({
  addresses,
  isLoading = false,
  isError = false,
  errorMessage,
  onRetry,
  onDelete,
  onEdit,
}: AddressListProps) {
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div role="status">
        <span className="sr-only">Loading your addresses…</span>
        {[0, 1].map((index) => (
          <div
            key={index}
            aria-hidden="true"
            className="mt-2 h-20 animate-pulse rounded bg-neutral-200 motion-reduce:animate-none"
          />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div>
        <Alert variant="error" message={errorMessage ?? DEFAULT_ERROR_MESSAGE} />
        {onRetry && (
          <Button onClick={onRetry} className="mt-2">
            Retry
          </Button>
        )}
      </div>
    );
  }

  if (addresses.length === 0) {
    return <EmptyState message={EMPTY_MESSAGE} />;
  }

  return (
    <>
      <ul className="grid grid-cols-1 gap-4 tablet:grid-cols-2">
        {addresses.map((address) => (
          <li key={address.id}>
            <AddressCard address={address} onEdit={onEdit} onDelete={setDeleteTargetId} />
          </li>
        ))}
      </ul>

      <ConfirmDialog
        open={deleteTargetId !== null}
        title="Delete address"
        description="This address will be permanently removed from your address book."
        confirmLabel="Confirm"
        onConfirm={() => {
          if (deleteTargetId) {
            onDelete(deleteTargetId);
          }
          setDeleteTargetId(null);
        }}
        onCancel={() => setDeleteTargetId(null)}
      />
    </>
  );
}
