import { apiClient } from "@/lib/api/apiClient";
import { adminRequest } from "@/lib/admin/adminRequest";
import type {
  ReferenceDataCreateInput,
  ReferenceDataResource,
  ReferenceDataUpdateInput,
  RawReferenceDetail,
  RawReferencePage,
} from "./referenceDataAdminTypes";

// P1-5 — one generic client parameterized by resource, since the three
// endpoint families are byte-for-byte identical apart from the path
// segment and whether `slug` is a valid field (categories only).
function basePath(resource: ReferenceDataResource): string {
  return `/api/v1/admin/${resource}`;
}

async function list(resource: ReferenceDataResource, includeDeleted = false, cursor?: string): Promise<RawReferencePage> {
  const search = new URLSearchParams();
  search.set("limit", "100");
  if (includeDeleted) search.set("include_deleted", "true");
  if (cursor) search.set("cursor", cursor);
  return adminRequest(() => apiClient.get<RawReferencePage>(`${basePath(resource)}?${search.toString()}`));
}

function buildWriteBody(resource: ReferenceDataResource, input: ReferenceDataCreateInput | ReferenceDataUpdateInput) {
  const body: Record<string, unknown> = {};
  if (input.name !== undefined) body.name = input.name;
  if (resource === "categories" && input.slug !== undefined) body.slug = input.slug;
  if (input.isActive !== undefined) body.is_active = input.isActive;
  return body;
}

async function create(resource: ReferenceDataResource, input: ReferenceDataCreateInput): Promise<RawReferenceDetail> {
  return adminRequest(() =>
    apiClient.post<RawReferenceDetail>(basePath(resource), buildWriteBody(resource, input), { csrf: true })
  );
}

async function update(
  resource: ReferenceDataResource,
  id: string,
  input: ReferenceDataUpdateInput
): Promise<RawReferenceDetail> {
  return adminRequest(() =>
    apiClient.patch<RawReferenceDetail>(
      `${basePath(resource)}/${encodeURIComponent(id)}`,
      buildWriteBody(resource, input),
      { csrf: true }
    )
  );
}

// Permanent archive — never a restore path (AGENTS.md: "Archive is
// permanent"). 204, no body.
async function archive(resource: ReferenceDataResource, id: string): Promise<void> {
  await adminRequest(() => apiClient.del(`${basePath(resource)}/${encodeURIComponent(id)}`, { csrf: true }));
}

export const referenceDataAdminApi = { list, create, update, archive };

export const referenceDataAdminKeys = {
  root: (resource: ReferenceDataResource) => ["admin", resource] as const,
  list: (resource: ReferenceDataResource) => ["admin", resource, "list"] as const,
};
