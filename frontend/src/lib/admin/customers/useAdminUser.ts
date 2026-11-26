import { useQuery } from "@tanstack/react-query";
import type { ApiError } from "@/lib/api/ApiError";
import { customersApi, customersKeys } from "./customersApi";
import type { AdminUserDetail } from "./customerTypes";

export function useAdminUser(userId: string) {
  return useQuery<AdminUserDetail, ApiError>({
    queryKey: customersKeys.detail(userId),
    queryFn: () => customersApi.getUser(userId),
  });
}
