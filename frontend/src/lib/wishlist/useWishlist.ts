import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ApiError } from "@/lib/api/ApiError";
import { useAuth } from "@/lib/auth/AuthProvider";
import { wishlistApi, wishlistKeys, type WishlistItemDTO } from "./wishlistApi";

// #ARCHITECTURE-WISHLIST-QUERIES (phase 6D)
//
// Read: enabled only for a signed-in viewer (there is no guest wishlist and
// no local copy). A 401 is final; a transport/5xx failure is retried once.
//
// Write: PUT or DELETE, then the server's state is read back before the
// mutation settles, so every heart and the account list show the same
// server-confirmed answer. A removal also drops the row from the cache at
// once (the 204 already confirms it is gone). Never retried automatically.

function retryOnce(failureCount: number, error: unknown): boolean {
  const e = error as ApiError | undefined;
  return !(e?.kind === "http" && e.status !== undefined && e.status < 500) && failureCount < 1;
}

export function useWishlist() {
  const { user } = useAuth();
  return useQuery<WishlistItemDTO[], ApiError>({
    queryKey: wishlistKeys.all(),
    queryFn: () => wishlistApi.listAll(),
    enabled: Boolean(user),
    retry: retryOnce,
  });
}

export interface WishlistToggle {
  productId: string;
  save: boolean;
}

export function useToggleWishlist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ productId, save }: WishlistToggle) => (save ? wishlistApi.add(productId) : wishlistApi.remove(productId)),
    retry: false,
    onSuccess: async (_data, { productId, save }) => {
      if (!save) {
        queryClient.setQueryData<WishlistItemDTO[]>(wishlistKeys.all(), (items) => items?.filter((item) => item.product_id !== productId));
      }
      await queryClient.invalidateQueries({ queryKey: wishlistKeys.root });
    },
  });
}

export const WISHLIST_MESSAGES = {
  generic: "We couldn't update your wishlist. Please try again.",
  csrf: "Unable to verify your session. Please refresh the page and try again.",
  verifyEmail: "Verify your email address to save products to your wishlist.",
  sessionExpired: "Your session has expired. Please sign in again.",
  notAvailable: "This product is no longer available, so it can't be saved.",
  rateLimited: "Too many wishlist changes. Please wait a while and try again.",
  loadFailed: "We couldn't load your wishlist. Please try again.",
} as const;

// Status + Problem.code only; the server's title/detail are never shown.
export function describeWishlistError(error: unknown): { message: string; refetchAuth: boolean } {
  const e = error as ApiError | undefined;
  if (e?.kind === "csrf") return { message: WISHLIST_MESSAGES.csrf, refetchAuth: false };
  if (e?.kind !== "http") return { message: WISHLIST_MESSAGES.generic, refetchAuth: false };
  switch (`${e.status} ${e.code ?? ""}`) {
    case "403 CSRF_INVALID":
      return { message: WISHLIST_MESSAGES.csrf, refetchAuth: false };
    case "403 EMAIL_VERIFICATION_REQUIRED":
      return { message: WISHLIST_MESSAGES.verifyEmail, refetchAuth: true };
    case "401 AUTH_REQUIRED":
      return { message: WISHLIST_MESSAGES.sessionExpired, refetchAuth: false };
    case "404 NOT_FOUND":
      return { message: WISHLIST_MESSAGES.notAvailable, refetchAuth: false };
    case "429 RATE_LIMITED":
      return { message: WISHLIST_MESSAGES.rateLimited, refetchAuth: false };
    default:
      return { message: WISHLIST_MESSAGES.generic, refetchAuth: false };
  }
}
