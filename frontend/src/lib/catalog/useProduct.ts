import { useQuery } from "@tanstack/react-query";
import type { ApiError } from "@/lib/api/ApiError";
import { productsApi, productsKeys } from "./productsApi";
import type { ProductDetail } from "./productTypes";

// Product detail is keyed by slug (B3) — a 404 (hidden/deleted/disabled-
// category/renamed product) is a real, expected outcome, not a transient
// fault, so this hook never retries on failure; the caller branches on
// `error.status === 404` to render the not-found experience vs. a generic
// retryable error (bekaa3d-api-contract: branch on the server's own
// status/code, never guess).
export function useProduct(slug: string) {
  return useQuery<ProductDetail, ApiError>({
    queryKey: productsKeys.detail(slug),
    queryFn: () => productsApi.getProductBySlug(slug),
    retry: false,
  });
}
