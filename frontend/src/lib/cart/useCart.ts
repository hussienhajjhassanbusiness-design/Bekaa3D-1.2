import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useAuth } from "@/lib/auth/AuthProvider";
import { cartApi } from "./cartApi";
import { describeCartWriteError } from "./cartErrors";
import { cartKeys } from "./cartKeys";
import { adaptCart } from "./cartModel";
import type { CartReadDTO } from "./cartTypes";

// #ARCHITECTURE-CANONICAL-CART-QUERY
//
// One query per signed-in user (cartKeys.current(userId)); anonymous
// visitors never request it. Writes are deliberately NOT optimistic: the
// server decides merges, caps, STL quantity and purchasability, so the UI
// shows a pending state and then the server's answer. POST/PATCH return
// a full CartRead, which is written into the canonical key verbatim; the
// whole cart family is then invalidated so the UI always ends on a fresh
// server read, even if two responses arrive out of order. DELETE (204)
// only invalidates. Writes are never retried automatically.

const STALE_TIME_MS = 30_000;

export function useCart() {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  return useQuery({
    queryKey: cartKeys.current(userId ?? "anonymous"),
    queryFn: () => cartApi.getCart(),
    enabled: userId !== null,
    select: adaptCart,
    staleTime: STALE_TIME_MS,
  });
}

function refetchCart(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: cartKeys.root });
}

function useWriteOptions() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  return {
    onSuccess: (data: CartReadDTO | void) => {
      if (user && data) {
        queryClient.setQueryData<CartReadDTO>(cartKeys.current(user.id), data);
      }
      return refetchCart(queryClient);
    },
    onError: (error: unknown) => {
      if (describeCartWriteError(error).refetch) {
        void refetchCart(queryClient);
      }
    },
    retry: false as const,
  };
}

export interface AddToCartInput {
  productId: string;
  quantity: number;
}

export function useAddToCart() {
  const options = useWriteOptions();
  return useMutation({
    mutationFn: ({ productId, quantity }: AddToCartInput) => cartApi.addItem({ product_id: productId, quantity }),
    ...options,
  });
}

export interface SetCartItemQuantityInput {
  productId: string;
  quantity: number;
}

export function useSetCartItemQuantity() {
  const options = useWriteOptions();
  return useMutation({
    mutationFn: ({ productId, quantity }: SetCartItemQuantityInput) => cartApi.setItemQuantity(productId, quantity),
    ...options,
  });
}

export function useRemoveCartItem() {
  const options = useWriteOptions();
  return useMutation({
    mutationFn: ({ productId }: { productId: string }) => cartApi.removeItem(productId),
    ...options,
  });
}
