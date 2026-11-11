"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { Alert } from "@/components/feedback/Alert";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { Button } from "@/components/forms/Button";
import { StatusBadge, describeAdminAccountStatus } from "@/components/admin/StatusBadge";
import { NotFoundContent } from "@/components/feedback/NotFoundContent";
import { useAdminUser } from "@/lib/admin/customers/useAdminUser";
import { useAdminUserUpdate } from "@/lib/admin/customers/useAdminUserUpdate";
import { describeAdminError } from "@/lib/admin/adminErrorMessages";

const LOAD_ERROR_MESSAGE = "Couldn't load this customer. Please try again.";

function isNotFound(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "kind" in error &&
    (error as { kind: unknown }).kind === "http" &&
    (error as { status?: unknown }).status === 404
  );
}

export default function AdminCustomerDetailPage() {
  const params = useParams<{ id: string }>();
  const userId = params.id;
  const { data: user, isLoading, isError, error } = useAdminUser(userId);
  const updateMutation = useAdminUserUpdate();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  if (isLoading) {
    return <LoadingSpinner />;
  }

  if (isError) {
    // A customer id that genuinely doesn't exist and a transport error
    // both land here; only the former is a real not-found.
    return isNotFound(error) ? <NotFoundContent /> : <Alert variant="error" message={LOAD_ERROR_MESSAGE} />;
  }

  if (!user) {
    return <NotFoundContent />;
  }

  const { label, tone } = describeAdminAccountStatus(user.is_active ? "active" : "deactivated");
  const actionLabel = user.is_active ? "Deactivate" : "Reactivate";

  async function handleConfirm() {
    setActionError(null);
    try {
      await updateMutation.mutateAsync({ userId: user!.id, isActive: !user!.is_active });
      setConfirmOpen(false);
    } catch (error) {
      setActionError(describeAdminError(error));
      setConfirmOpen(false);
    }
  }

  return (
    <>
      <h1 className="text-h1 font-bold text-text-primary">{user.email}</h1>
      {actionError && <Alert variant="error" message={actionError} />}

      <dl className="mt-4 grid gap-3 tablet:grid-cols-2">
        <div>
          <dt className="text-label font-semibold uppercase tracking-label text-text-secondary">Status</dt>
          <dd className="mt-1">
            <StatusBadge label={label} tone={tone} />
          </dd>
        </div>
        <div>
          <dt className="text-label font-semibold uppercase tracking-label text-text-secondary">Role</dt>
          <dd className="mt-1 text-body text-text-primary">{user.role}</dd>
        </div>
        <div>
          <dt className="text-label font-semibold uppercase tracking-label text-text-secondary">Email verified</dt>
          <dd className="mt-1 text-body text-text-primary">{user.email_verified_at ? "Yes" : "No"}</dd>
        </div>
        <div>
          <dt className="text-label font-semibold uppercase tracking-label text-text-secondary">Joined</dt>
          <dd className="mt-1 text-body text-text-primary">{new Date(user.created_at).toLocaleDateString()}</dd>
        </div>
      </dl>

      <nav aria-label="Customer records" className="mt-4 flex flex-wrap gap-4 text-body">
        <Link href={`/admin/orders?customer_id=${user.id}`} className="text-text-link underline">
          Orders
        </Link>
        <Link href={`/admin/refunds?customer_id=${user.id}&queue=false`} className="text-text-link underline">
          Refunds
        </Link>
        <Link href={`/admin/cash-blocks?customer_id=${user.id}`} className="text-text-link underline">
          Cash blocks
        </Link>
      </nav>

      <Button className="mt-6" onClick={() => setConfirmOpen(true)}>
        {actionLabel}
      </Button>

      <ConfirmDialog
        open={confirmOpen}
        title={`${actionLabel} this customer?`}
        description={
          user.is_active
            ? "This immediately revokes all of this customer's active sessions. They will need to log in again if reactivated."
            : "This restores the customer's access. Any previously revoked sessions stay revoked — they will need to log in again."
        }
        confirmLabel={actionLabel}
        isConfirming={updateMutation.isPending}
        onConfirm={() => void handleConfirm()}
        onCancel={() => setConfirmOpen(false)}
      />
    </>
  );
}
