"use client";

import { useRef, useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AdminBackLink } from "@/components/admin/adminUi";
import { PromotionForm } from "@/components/admin/promotions/PromotionForm";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { Alert } from "@/components/feedback/Alert";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { NotFoundContent } from "@/components/feedback/NotFoundContent";
import { describeAdminError } from "@/lib/admin/adminErrorMessages";
import {
  describePromotionError,
  promotionFormFrom,
  toPromotionWrite,
  validatePromotionForm,
  type PromotionFormErrors,
  type PromotionFormValues,
} from "@/lib/admin/promotions/promotionForm";
import { adminPromotionKeys, promotionsAdminApi } from "@/lib/admin/promotions/promotionsAdminApi";
import type { ApiError } from "@/lib/api/ApiError";
import { isOrderId } from "@/lib/orders/orderModel";
import { describePromotionStatus } from "@/lib/promotions/promotionFormat";
import { promotionKeys } from "@/lib/promotions/promotionsApi";
import type { AdminPromotionRead } from "@/lib/promotions/promotionTypes";

// /admin/promotions/[id] — edit one promotion (PATCH, the whole form) or
// switch it off with the Active switch. No delete exists in the contract.
export default function AdminPromotionPage() {
  const params = useParams<{ id: string }>();
  const id = typeof params.id === "string" ? params.id : "";
  const validId = isOrderId(id);
  const queryClient = useQueryClient();
  const detail = useQuery<AdminPromotionRead, ApiError>({
    queryKey: adminPromotionKeys.detail(id),
    queryFn: () => promotionsAdminApi.getPromotion(id),
    enabled: validId,
  });
  const [form, setForm] = useState<PromotionFormValues | null>(null);
  const [loadedFrom, setLoadedFrom] = useState<AdminPromotionRead | undefined>(undefined);
  const [errors, setErrors] = useState<PromotionFormErrors | undefined>(undefined);
  const [banner, setBanner] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const inFlight = useRef(false);

  // The form starts from the server's promotion, and re-bases on each save's
  // response; a background refetch never overwrites an edit in progress.
  if (detail.data && loadedFrom === undefined) {
    setLoadedFrom(detail.data);
    setForm(promotionFormFrom(detail.data));
  }

  if (!validId) return <NotFoundContent />;
  if (detail.isLoading) return <LoadingSpinner />;
  if (detail.isError) {
    return detail.error.kind === "http" && (detail.error.status === 404 || detail.error.status === 422) ? (
      <NotFoundContent />
    ) : (
      <Alert variant="error" message={describeAdminError(detail.error)} />
    );
  }
  const promotion = detail.data;
  if (!promotion || !form) return <LoadingSpinner />;
  const status = describePromotionStatus(promotion.status);

  async function handleSubmit() {
    if (inFlight.current || !form) return;
    setBanner(null);
    setSaved(false);
    const local = validatePromotionForm(form);
    if (Object.keys(local).length > 0) {
      setErrors(local);
      return;
    }
    setErrors(undefined);
    inFlight.current = true;
    setIsSubmitting(true);
    try {
      const updated = await promotionsAdminApi.updatePromotion(id, toPromotionWrite(form));
      queryClient.setQueryData(adminPromotionKeys.detail(id), updated);
      void queryClient.invalidateQueries({ queryKey: adminPromotionKeys.list() });
      void queryClient.invalidateQueries({ queryKey: promotionKeys.root });
      setLoadedFrom(updated);
      setForm(promotionFormFrom(updated));
      setSaved(true);
    } catch (error) {
      const result = describePromotionError(error);
      setErrors(result.fieldErrors);
      setBanner(result.banner ?? null);
    } finally {
      inFlight.current = false;
      setIsSubmitting(false);
    }
  }

  return (
    <>
      <div>
        <AdminBackLink href="/admin/promotions">Promotions</AdminBackLink>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <h1 className="break-words font-headline text-headline-lg text-on-surface">{promotion.name}</h1>
        <StatusBadge label={status.label} tone={status.tone} />
      </div>
      <p
        role="status"
        aria-live="polite"
        className="mt-4 rounded-card border border-primary/20 border-l-4 border-l-primary bg-surface-container-low p-4 font-body text-body-md text-on-surface empty:hidden"
      >
        {saved ? "Promotion saved." : ""}
      </p>
      {banner && (
        <div className="mt-4">
          <Alert variant="error" message={banner} />
        </div>
      )}
      <div className="mt-6">
        <PromotionForm
          value={form}
          onChange={(next) => {
            setSaved(false);
            setForm(next);
          }}
          errors={errors}
          isSubmitting={isSubmitting}
          submitLabel="Save promotion"
          onSubmit={() => void handleSubmit()}
        />
      </div>
    </>
  );
}
