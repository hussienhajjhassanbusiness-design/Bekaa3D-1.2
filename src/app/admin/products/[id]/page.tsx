"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { Alert } from "@/components/feedback/Alert";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { Button } from "@/components/forms/Button";
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
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-h1 font-bold text-text-primary">{product.name}</h1>
        <div className="flex gap-2">
          <Link href={`/admin/products/${product.id}/edit`}>
            <Button type="button">Edit</Button>
          </Link>
          <Button type="button" variant="destructive" onClick={() => setConfirmOpen(true)}>
            Delete
          </Button>
        </div>
      </div>

      {deleteError && <Alert variant="error" message={deleteError} />}

      <dl className="mt-4 grid gap-3 tablet:grid-cols-2">
        <div>
          <dt className="text-label font-semibold uppercase tracking-label text-text-secondary">Type</dt>
          <dd className="mt-1 text-body text-text-primary">{product.type === "physical" ? "Physical" : "STL"}</dd>
        </div>
        <div>
          <dt className="text-label font-semibold uppercase tracking-label text-text-secondary">Price</dt>
          <dd className="mt-1 text-body text-text-primary">
            <PriceDisplay amountCents={product.price.amount_cents} currency={product.price.currency} />
          </dd>
        </div>
        <div>
          <dt className="text-label font-semibold uppercase tracking-label text-text-secondary">Visibility</dt>
          <dd className="mt-1">
            <StatusBadge label={product.is_visible ? "Visible" : "Hidden"} tone={product.is_visible ? "positive" : "neutral"} />
          </dd>
        </div>
        <div>
          <dt className="text-label font-semibold uppercase tracking-label text-text-secondary">Availability</dt>
          <dd className="mt-1">
            <StatusBadge
              label={product.is_available ? "Available" : "Unavailable"}
              tone={product.is_available ? "positive" : "warning"}
            />
          </dd>
        </div>
        <div>
          <dt className="text-label font-semibold uppercase tracking-label text-text-secondary">Slug</dt>
          <dd className="mt-1 text-body text-text-primary">{product.slug}</dd>
        </div>
        <div>
          <dt className="text-label font-semibold uppercase tracking-label text-text-secondary">Images</dt>
          <dd className="mt-1 text-body text-text-primary">{product.images.length}</dd>
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
