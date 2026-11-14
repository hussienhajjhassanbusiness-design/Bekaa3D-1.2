"use client";

import { useState } from "react";
import { Alert } from "@/components/feedback/Alert";
import { ReferenceDataManager } from "./ReferenceDataManager";
import type { ReferenceDataDraft, ReferenceDataEntityConfig, ReferenceDataFieldErrors } from "./referenceDataTypes";
import {
  useReferenceDataCreate,
  useReferenceDataList,
  useReferenceDataUpdate,
  useReferenceDataArchive,
} from "@/lib/admin/referenceData/useReferenceData";
import { describeReferenceDataError, toCreateInput } from "@/lib/admin/referenceData/referenceDataAdapter";
import type { ReferenceDataResource } from "@/lib/admin/referenceData/referenceDataAdminTypes";

export interface AdminReferenceDataPageProps {
  resource: ReferenceDataResource;
  config: ReferenceDataEntityConfig;
}

// Wires the generic presentational ReferenceDataManager (FVS-010) to the
// real admin CRUD contract (P1-5) — the one place categories/materials/
// colours pages differ is which `resource`/`config` they pass in here.
export function AdminReferenceDataPage({ resource, config }: AdminReferenceDataPageProps) {
  // Archived rows stay visible with a badge rather than disappearing
  // (AGENTS.md) — always fetched, never a filter toggle.
  const { data: entries, isLoading, isError } = useReferenceDataList(resource, true);
  const createMutation = useReferenceDataCreate(resource);
  const updateMutation = useReferenceDataUpdate(resource);
  const archiveMutation = useReferenceDataArchive(resource);

  const [fieldErrors, setFieldErrors] = useState<ReferenceDataFieldErrors | undefined>(undefined);
  const [bannerMessage, setBannerMessage] = useState<string | null>(null);

  async function handleSave(draft: ReferenceDataDraft, editingId: string | null) {
    setFieldErrors(undefined);
    setBannerMessage(null);
    try {
      if (editingId) {
        await updateMutation.mutateAsync({
          id: editingId,
          input: { name: draft.name, slug: resource === "categories" ? draft.swatchValue : undefined },
        });
      } else {
        await createMutation.mutateAsync(toCreateInput(resource, draft));
      }
    } catch (error) {
      const result = describeReferenceDataError(resource, error);
      if (result.fieldErrors) {
        setFieldErrors(result.fieldErrors);
      } else {
        setBannerMessage(result.bannerMessage ?? null);
      }
    }
  }

  async function handleArchive(id: string) {
    setBannerMessage(null);
    try {
      await archiveMutation.mutateAsync(id);
    } catch (error) {
      setBannerMessage(describeReferenceDataError(resource, error).bannerMessage ?? null);
    }
  }

  async function handleToggleActive(id: string, nextIsActive: boolean) {
    setBannerMessage(null);
    try {
      await updateMutation.mutateAsync({ id, input: { isActive: nextIsActive } });
    } catch (error) {
      setBannerMessage(describeReferenceDataError(resource, error).bannerMessage ?? null);
    }
  }

  if (isError) {
    return (
      <Alert variant="error" message={`Couldn't load ${config.entityLabelPlural.toLowerCase()}. Please try again.`} />
    );
  }

  return (
    <>
      {bannerMessage && (
        <div className="mb-4">
          <Alert variant="error" message={bannerMessage} />
        </div>
      )}
      <ReferenceDataManager
        config={config}
        entries={entries ?? []}
        isLoading={isLoading}
        isSaving={createMutation.isPending || updateMutation.isPending}
        isArchiving={archiveMutation.isPending}
        isTogglingActive={updateMutation.isPending}
        fieldErrors={fieldErrors}
        onSave={(draft, editingId) => void handleSave(draft, editingId)}
        onArchive={(id) => void handleArchive(id)}
        onToggleActive={(id, nextIsActive) => void handleToggleActive(id, nextIsActive)}
      />
    </>
  );
}
