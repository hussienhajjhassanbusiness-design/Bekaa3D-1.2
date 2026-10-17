import { apiClient } from "@/lib/api/apiClient";
import { adminRequest } from "@/lib/admin/adminRequest";
import type { RawProductImage } from "./productAdminTypes";

// P1-7 — every image mutation is synchronous: a 201/200 means
// scan+re-encode+store already succeeded, there is no pending/polling
// state (AGENTS.md: "Do not build an async scan status UI"). None of
// these change the product's own `version`.
function imagesPath(productId: string): string {
  return `/api/v1/admin/products/${encodeURIComponent(productId)}/images`;
}

async function uploadImage(productId: string, file: File, altText?: string): Promise<RawProductImage> {
  const formData = new FormData();
  formData.set("file", file);
  if (altText) {
    formData.set("alt_text", altText);
  }
  return adminRequest(() => apiClient.postForm<RawProductImage>(imagesPath(productId), formData, { csrf: true }));
}

async function updateAltText(productId: string, imageId: string, altText: string | null): Promise<RawProductImage> {
  return adminRequest(() =>
    apiClient.patch<RawProductImage>(
      `${imagesPath(productId)}/${encodeURIComponent(imageId)}`,
      { alt_text: altText },
      { csrf: true }
    )
  );
}

// Confirmed PUT (openapi.json), 200 -> ProductImageRead.
async function setCover(productId: string, imageId: string): Promise<RawProductImage> {
  return adminRequest(() =>
    apiClient.put<RawProductImage>(`${imagesPath(productId)}/${encodeURIComponent(imageId)}/cover`, undefined, {
      csrf: true,
    })
  );
}

// Confirmed PUT with body {image_ids}, response {items: ProductImageRead[]}
// — must name every live image exactly once or the backend answers 422.
async function reorder(productId: string, imageIds: string[]): Promise<RawProductImage[]> {
  const response = await adminRequest(() =>
    apiClient.put<{ items: RawProductImage[] }>(`${imagesPath(productId)}/order`, { image_ids: imageIds }, { csrf: true })
  );
  return response.items;
}

async function deleteImage(productId: string, imageId: string): Promise<void> {
  await adminRequest(() => apiClient.del(`${imagesPath(productId)}/${encodeURIComponent(imageId)}`, { csrf: true }));
}

export const productImagesAdminApi = { uploadImage, updateAltText, setCover, reorder, deleteImage };
