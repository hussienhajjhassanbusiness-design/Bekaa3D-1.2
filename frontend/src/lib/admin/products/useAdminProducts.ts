import { useQuery } from "@tanstack/react-query";
import type { ApiError } from "@/lib/api/ApiError";
import { productsAdminApi, productsAdminKeys } from "./productsAdminApi";
import type { AdminProductsQueryParams, RawAdminProductPage } from "./productAdminTypes";

export function useAdminProducts(params: AdminProductsQueryParams) {
  return useQuery<RawAdminProductPage, ApiError>({
    queryKey: productsAdminKeys.list(params),
    queryFn: () => productsAdminApi.listProducts(params),
  });
}
