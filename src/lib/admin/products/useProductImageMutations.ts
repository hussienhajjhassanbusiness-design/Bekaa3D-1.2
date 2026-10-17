import { useMutation, useQueryClient } from "@tanstack/react-query";
import { productImagesAdminApi } from "./productImagesAdminApi";
import { productsAdminKeys } from "./productsAdminApi";

// Every image mutation invalidates the product detail query (which
// embeds `images`) rather than maintaining a separate images cache —
// image mutations never change the product's own `version` (P1-7), so
// there's no concurrency concern in refetching this way.
function useInvalidateProduct(productId: string) {
  const queryClient = useQueryClient();
  return () => void queryClient.invalidateQueries({ queryKey: productsAdminKeys.detail(productId) });
}

export function useProductImageUpload(productId: string) {
  const invalidate = useInvalidateProduct(productId);
  return useMutation({
    mutationFn: ({ file, altText }: { file: File; altText?: string }) =>
      productImagesAdminApi.uploadImage(productId, file, altText),
    onSuccess: invalidate,
  });
}

export function useProductImageAltTextUpdate(productId: string) {
  const invalidate = useInvalidateProduct(productId);
  return useMutation({
    mutationFn: ({ imageId, altText }: { imageId: string; altText: string | null }) =>
      productImagesAdminApi.updateAltText(productId, imageId, altText),
    onSuccess: invalidate,
  });
}

export function useProductImageSetCover(productId: string) {
  const invalidate = useInvalidateProduct(productId);
  return useMutation({
    mutationFn: (imageId: string) => productImagesAdminApi.setCover(productId, imageId),
    onSuccess: invalidate,
  });
}

export function useProductImageReorder(productId: string) {
  const invalidate = useInvalidateProduct(productId);
  return useMutation({
    mutationFn: (imageIds: string[]) => productImagesAdminApi.reorder(productId, imageIds),
    onSuccess: invalidate,
  });
}

export function useProductImageDelete(productId: string) {
  const invalidate = useInvalidateProduct(productId);
  return useMutation({
    mutationFn: (imageId: string) => productImagesAdminApi.deleteImage(productId, imageId),
    onSuccess: invalidate,
  });
}
