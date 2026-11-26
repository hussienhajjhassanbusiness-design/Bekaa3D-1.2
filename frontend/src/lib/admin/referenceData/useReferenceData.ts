import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ApiError } from "@/lib/api/ApiError";
import type { ReferenceDataEntry } from "@/components/admin/referenceDataTypes";
import { referenceDataAdminApi, referenceDataAdminKeys } from "./referenceDataAdminApi";
import { toReferenceDataEntry } from "./referenceDataAdapter";
import type { ReferenceDataResource, RawReferencePage, ReferenceDataCreateInput, ReferenceDataUpdateInput } from "./referenceDataAdminTypes";

// One generic hook family parameterized by resource — categories,
// materials, and colours share byte-for-byte identical CRUD mechanics
// (P1-5), so a page for any of the three only ever supplies its own
// `resource` literal, never a separately-written data layer.
export function useReferenceDataList(resource: ReferenceDataResource, includeDeleted: boolean) {
  return useQuery<RawReferencePage, ApiError, ReferenceDataEntry[]>({
    queryKey: [...referenceDataAdminKeys.list(resource), includeDeleted],
    queryFn: () => referenceDataAdminApi.list(resource, includeDeleted),
    select: (page) => page.items.map(toReferenceDataEntry),
  });
}

function useInvalidateReferenceData(resource: ReferenceDataResource) {
  const queryClient = useQueryClient();
  return () => void queryClient.invalidateQueries({ queryKey: referenceDataAdminKeys.root(resource) });
}

export function useReferenceDataCreate(resource: ReferenceDataResource) {
  const invalidate = useInvalidateReferenceData(resource);
  return useMutation({
    mutationFn: (input: ReferenceDataCreateInput) => referenceDataAdminApi.create(resource, input),
    onSuccess: invalidate,
  });
}

export function useReferenceDataUpdate(resource: ReferenceDataResource) {
  const invalidate = useInvalidateReferenceData(resource);
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: ReferenceDataUpdateInput }) =>
      referenceDataAdminApi.update(resource, id, input),
    onSuccess: invalidate,
  });
}

export function useReferenceDataArchive(resource: ReferenceDataResource) {
  const invalidate = useInvalidateReferenceData(resource);
  return useMutation({
    mutationFn: (id: string) => referenceDataAdminApi.archive(resource, id),
    onSuccess: invalidate,
  });
}
