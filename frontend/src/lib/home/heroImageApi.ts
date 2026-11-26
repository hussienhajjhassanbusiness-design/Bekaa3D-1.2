import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/apiClient";
import { settingsApi, settingsKeys } from "@/lib/admin/settings/settingsApi";
import type { UploadValidationConfig } from "@/components/forms/uploadTypes";
import { describeAdminError } from "@/lib/admin/adminErrorMessages";

// The homepage hero image (backend docs/homepage-hero-image.md). The backend
// owns the image: an administrator uploads it, the backend scans, re-encodes
// and stores it, and points the `homepage_hero_image` setting at it.
// `url: null` means none is set, and the hero shows its default brand visual.
export interface HeroImageRead {
  url: string | null;
}

// The setting this image is stored in. The Store Settings page leaves it out
// of the generic controls: it is set by uploading a file, never by typing.
export const HERO_IMAGE_SETTING_KEY = "homepage_hero_image";

// Local fast feedback only. The backend decides from the file's content, and
// also refuses images under 400 px on a side.
export const HERO_IMAGE_UPLOAD_CONFIG: UploadValidationConfig = {
  allowedMimeTypes: ["image/jpeg", "image/png", "image/webp"],
  maxBytes: 10 * 1024 * 1024,
  maxFiles: 1,
};
export const HERO_IMAGE_REQUIREMENTS = "JPEG, PNG or WebP, up to 10 MB, at least 400 × 400 px.";

// GET /api/v1/home/hero-image (public, rate limited).
function getHeroImage(): Promise<HeroImageRead> {
  return apiClient.get<HeroImageRead>("/api/v1/home/hero-image");
}

// PUT /api/v1/admin/home/hero-image (admin + MFA, CSRF, multipart `file`).
// A refusal (422 UPLOAD_REJECTED / MALWARE_DETECTED, 503) leaves the saved
// image as it was.
function replaceHeroImage(file: File): Promise<HeroImageRead> {
  const formData = new FormData();
  formData.set("file", file);
  return apiClient.putForm<HeroImageRead>("/api/v1/admin/home/hero-image", formData, { csrf: true });
}

export const heroImageApi = { getHeroImage, replaceHeroImage };

export const heroImageKeys = {
  root: ["home", "hero-image"] as const,
};

export function useHeroImage() {
  return useQuery({
    queryKey: heroImageKeys.root,
    queryFn: heroImageApi.getHeroImage,
    staleTime: 60_000,
  });
}

export function useReplaceHeroImage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: heroImageApi.replaceHeroImage,
    onSuccess: (saved) => {
      // The response is the stored image, so show it immediately. The
      // settings list holds the same value as a storage key, so refetch it too.
      queryClient.setQueryData<HeroImageRead>(heroImageKeys.root, saved);
      void queryClient.invalidateQueries({ queryKey: heroImageKeys.root });
      void queryClient.invalidateQueries({ queryKey: settingsKeys.list() });
    },
  });
}

// Restore the default brand visual: the existing settings PATCH with
// `homepage_hero_image: null` (the only value that endpoint accepts for it).
export function useRestoreDefaultHeroImage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => settingsApi.updateSetting(HERO_IMAGE_SETTING_KEY, null),
    onSuccess: () => {
      queryClient.setQueryData<HeroImageRead>(heroImageKeys.root, { url: null });
      void queryClient.invalidateQueries({ queryKey: heroImageKeys.root });
      void queryClient.invalidateQueries({ queryKey: settingsKeys.list() });
    },
  });
}

const KEPT = "Your current hero image is unchanged.";

// Branches on Problem.code only (bekaa3d-api-contract). Every refusal leaves
// the saved image in place, and the message says so.
export function describeHeroImageError(error: unknown): string {
  const code =
    typeof error === "object" && error !== null && "code" in error ? (error as { code?: unknown }).code : undefined;
  if (code === "UPLOAD_REJECTED") {
    return `This image couldn't be used. Choose a JPEG, PNG or WebP image up to 10 MB and at least 400 × 400 px. ${KEPT}`;
  }
  return `${describeAdminError(error)} ${KEPT}`;
}
