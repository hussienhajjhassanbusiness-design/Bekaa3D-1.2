"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { Alert } from "@/components/feedback/Alert";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { Button, buttonLinkClassName } from "@/components/forms/Button";
import { AdminBackLink } from "@/components/admin/adminUi";
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
      <div>
        <AdminBackLink href="/admin/customers">Customers</AdminBackLink>
      </div>
      <h1 className="mt-2 break-all font-headline text-headline-lg text-on-surface">{user.email}</h1>
      {actionError && (
        <div className="mt-4">
          <Alert variant="error" message={actionError} />
        </div>
      )}

      <dl className="mt-6 grid gap-4 rounded-card border border-outline-variant/40 bg-surface-container-lowest p-5 shadow-sm tablet:p-6 tablet:grid-cols-2">
        <div>
          <dt className="font-label text-label-sm uppercase text-on-surface-variant">Status</dt>
          <dd className="mt-1">
            <StatusBadge label={label} tone={tone} />
          </dd>
        </div>
        <div>
          <dt className="font-label text-label-sm uppercase text-on-surface-variant">Role</dt>
          <dd className="mt-1 font-body text-body-md capitalize text-on-surface">{user.role}</dd>
        </div>
        <div>
          <dt className="font-label text-label-sm uppercase text-on-surface-variant">Email verified</dt>
          <dd className="mt-1 text-body-md text-on-surface">{user.email_verified_at ? "Yes" : "No"}</dd>
        </div>
        <div>
          <dt className="font-label text-label-sm uppercase text-on-surface-variant">Joined</dt>
          <dd className="mt-1 text-body-md text-on-surface">{new Date(user.created_at).toLocaleDateString()}</dd>
        </div>
      </dl>

      <nav aria-label="Customer records" className="mt-6 flex flex-wrap gap-3">
        <Link href={`/admin/orders?customer_id=${user.id}`} className={buttonLinkClassName("outline")}>
          Orders
        </Link>
        <Link href={`/admin/refunds?customer_id=${user.id}&queue=false`} className={buttonLinkClassName("outline")}>
          Refunds
        </Link>
        <Link href={`/admin/cash-blocks?customer_id=${user.id}`} className={buttonLinkClassName("outline")}>
          Cash blocks
        </Link>
      </nav>

      <section
        aria-labelledby="customer-access-heading"
        className="mt-6 max-w-form rounded-card border border-error/30 border-t-4 border-t-error bg-surface-container-lowest p-5 shadow-sm tablet:p-6"
      >
        <h2 id="customer-access-heading" className="font-headline text-headline-md text-on-surface">
          Account access
        </h2>
        <Button
          className={`mt-4 ${user.is_active ? "text-error" : ""}`}
          variant={user.is_active ? "outline" : "primary"}
          onClick={() => setConfirmOpen(true)}
        >
          {actionLabel}
        </Button>
      </section>

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
