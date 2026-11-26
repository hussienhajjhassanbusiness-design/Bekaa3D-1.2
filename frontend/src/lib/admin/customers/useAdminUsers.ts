import { useQuery } from "@tanstack/react-query";
import type { ApiError } from "@/lib/api/ApiError";
import { customersApi, customersKeys } from "./customersApi";
import type { AdminUserPage, AdminUsersQueryParams } from "./customerTypes";

// Single-page-at-a-time (C2 cursor pagination, no page numbers/total) —
// the caller supplies the current page's cursor (from useCursorPagination)
// and gets back exactly that one page, matching AdminTable's controlled
// hasPrevious/hasNext/onPrevious/onNext props.
export function useAdminUsers(params: AdminUsersQueryParams) {
  return useQuery<AdminUserPage, ApiError>({
    queryKey: customersKeys.list(params),
    queryFn: () => customersApi.listUsers(params),
  });
}
