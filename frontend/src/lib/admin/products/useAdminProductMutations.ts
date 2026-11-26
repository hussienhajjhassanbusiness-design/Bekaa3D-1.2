import { useMutation, useQueryClient } from "@tanstack/react-query";
import { productsAdminApi, productsAdminKeys } from "./productsAdminApi";

export function useAdminProductCreate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => productsAdminApi.createProduct(body),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: productsAdminKeys.root }),
  });
}

export function useAdminProductUpdate(productId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => productsAdminApi.updateProduct(productId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: productsAdminKeys.root });
      void queryClient.invalidateQueries({ queryKey: productsAdminKeys.detail(productId) });
    },
  });
}

export function useAdminProductDelete() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ productId, version }: { productId: string; version: number }) =>
      productsAdminApi.deleteProduct(productId, version),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: productsAdminKeys.root }),
  });
}
