import { useQuery } from "@tanstack/react-query";
import type { ApiError } from "@/lib/api/ApiError";
import { productsAdminApi, productsAdminKeys } from "./productsAdminApi";
import type { RawAdminProductDetail } from "./productAdminTypes";

export function useAdminProduct(productId: string) {
  return useQuery<RawAdminProductDetail, ApiError>({
    queryKey: productsAdminKeys.detail(productId),
    queryFn: () => productsAdminApi.getProduct(productId),
  });
}
