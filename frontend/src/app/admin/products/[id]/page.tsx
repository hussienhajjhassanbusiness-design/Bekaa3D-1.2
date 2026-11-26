"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { Alert } from "@/components/feedback/Alert";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { Button, buttonLinkClassName } from "@/components/forms/Button";
import { AdminBackLink } from "@/components/admin/adminUi";
import { Icon } from "@/components/ui/Icon";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { NotFoundContent } from "@/components/feedback/NotFoundContent";
import { useAdminProduct } from "@/lib/admin/products/useAdminProduct";
import { useAdminProductDelete } from "@/lib/admin/products/useAdminProductMutations";
import { describeAdminError } from "@/lib/admin/adminErrorMessages";

const LOAD_ERROR_MESSAGE = "Couldn't load this product. Please try again.";

function isNotFound(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "kind" in error &&
    (error as { kind: unknown }).kind === "http" &&
    (error as { status?: unknown }).status === 404
  );
}

export default function AdminProductDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { data: product, isLoading, isError, error } = useAdminProduct(params.id);
  const deleteMutation = useAdminProductDelete();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  if (isLoading) {
    return <LoadingSpinner />;
  }

  if (isError) {
    return isNotFound(error) ? <NotFoundContent /> : <Alert variant="error" message={LOAD_ERROR_MESSAGE} />;
  }

  if (!product) {
    return <NotFoundContent />;
  }

  async function handleDelete() {
    setDeleteError(null);
    try {
      await deleteMutation.mutateAsync({ productId: product!.id, version: product!.version });
      router.push("/admin/products");
    } catch (error) {
      setConfirmOpen(false);
      setDeleteError(describeAdminError(error));
    }
  }

  return (
    <>
      <div>
        <AdminBackLink href="/admin/products">Products</AdminBackLink>
      </div>
      <div className="mt-2 flex flex-col gap-4 tablet:flex-row tablet:items-end tablet:justify-between">
        <h1 className="min-w-0 break-words font-headline text-headline-lg text-on-surface">{product.name}</h1>
        <div className="flex shrink-0 flex-wrap gap-3">
          <Button type="button" variant="outline" className="text-error" onClick={() => setConfirmOpen(true)}>
            <Icon name="delete" className="h-5 w-5" />
            Delete
          </Button>
          <Link href={`/admin/products/${product.id}/edit`} className={buttonLinkClassName("primary")}>
            <Icon name="edit" className="h-5 w-5" />
            Edit
          </Link>
        </div>
      </div>

      {deleteError && (
        <div className="mt-4">
          <Alert variant="error" message={deleteError} />
        </div>
      )}

      <dl className="mt-6 grid gap-4 rounded-card border border-outline-variant/40 bg-surface-container-lowest p-5 shadow-sm tablet:p-6 tablet:grid-cols-2">
        <div>
          <dt className="font-label text-label-sm uppercase text-on-surface-variant">Type</dt>
          <dd className="mt-1 text-body-md text-on-surface">{product.type === "physical" ? "Physical" : "STL"}</dd>
        </div>
        <div>
          <dt className="font-label text-label-sm uppercase text-on-surface-variant">Price</dt>
          <dd className="mt-1 text-body-md text-on-surface">
            <PriceDisplay amountCents={product.price.amount_cents} currency={product.price.currency} />
          </dd>
        </div>
        <div>
          <dt className="font-label text-label-sm uppercase text-on-surface-variant">Visibility</dt>
          <dd className="mt-1">
            <StatusBadge
              label={product.is_visible ? "Visible" : "Hidden"}
              tone={product.is_visible ? "positive" : "neutral"}
            />
          </dd>
        </div>
        <div>
          <dt className="font-label text-label-sm uppercase text-on-surface-variant">Availability</dt>
          <dd className="mt-1">
            <StatusBadge
              label={product.is_available ? "Available" : "Unavailable"}
              tone={product.is_available ? "positive" : "warning"}
            />
          </dd>
        </div>
        <div>
          <dt className="font-label text-label-sm uppercase text-on-surface-variant">Slug</dt>
          <dd className="mt-1 break-all font-label text-body-md text-on-surface">{product.slug}</dd>
        </div>
        <div>
          <dt className="font-label text-label-sm uppercase text-on-surface-variant">Images</dt>
          <dd className="mt-1 text-body-md text-on-surface">{product.images.length}</dd>
        </div>
      </dl>

      <ConfirmDialog
        open={confirmOpen}
        title="Delete this product?"
        description="This permanently removes the product from the catalogue. It cannot be restored."
        confirmLabel="Delete"
        isDestructive
        isConfirming={deleteMutation.isPending}
        onConfirm={() => void handleDelete()}
        onCancel={() => setConfirmOpen(false)}
      />
    </>
  );
}
