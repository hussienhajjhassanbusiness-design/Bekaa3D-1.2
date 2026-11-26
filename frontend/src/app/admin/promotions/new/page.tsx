"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { AdminBackLink } from "@/components/admin/adminUi";
import { PromotionForm } from "@/components/admin/promotions/PromotionForm";
import { Alert } from "@/components/feedback/Alert";
import {
  describePromotionError,
  emptyPromotionForm,
  toPromotionWrite,
  validatePromotionForm,
  type PromotionFormErrors,
} from "@/lib/admin/promotions/promotionForm";
import { adminPromotionKeys, promotionsAdminApi } from "@/lib/admin/promotions/promotionsAdminApi";
import { promotionKeys } from "@/lib/promotions/promotionsApi";

export default function AdminNewPromotionPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [form, setForm] = useState(() => emptyPromotionForm());
  const [errors, setErrors] = useState<PromotionFormErrors | undefined>(undefined);
  const [banner, setBanner] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const inFlight = useRef(false);

  async function handleSubmit() {
    if (inFlight.current) return;
    setBanner(null);
    const local = validatePromotionForm(form);
    if (Object.keys(local).length > 0) {
      setErrors(local);
      return;
    }
    setErrors(undefined);
    inFlight.current = true;
    setIsSubmitting(true);
    try {
      await promotionsAdminApi.createPromotion(toPromotionWrite(form));
      void queryClient.invalidateQueries({ queryKey: adminPromotionKeys.root });
      void queryClient.invalidateQueries({ queryKey: promotionKeys.root });
      router.push("/admin/promotions");
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
      <h1 className="mt-2 break-words font-headline text-headline-lg text-on-surface">New promotion</h1>
      {banner && (
        <div className="mt-4">
          <Alert variant="error" message={banner} />
        </div>
      )}
      <div className="mt-6">
        <PromotionForm
          value={form}
          onChange={setForm}
          errors={errors}
          isSubmitting={isSubmitting}
          submitLabel="Save promotion"
          onSubmit={() => void handleSubmit()}
        />
      </div>
    </>
  );
}
