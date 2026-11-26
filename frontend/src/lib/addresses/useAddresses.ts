import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import type { ApiError } from "@/lib/api/ApiError";
import { addressesApi } from "./addressesApi";
import { addressKeys } from "./addressKeys";
import { adaptAddress } from "./addressModel";
import type { AddressCreateDTO, AddressUpdateDTO } from "./addressTypes";

// #ARCHITECTURE-CANONICAL-ADDRESSES-QUERY — one list query; every write
// invalidates the whole `addressKeys.root` family so the UI always ends
// on server truth. A default switch, a create with is_default, or
// deleting the default all change OTHER rows too, so a refetch (not a
// local patch of one row) is the correct strategy. Writes are never
// retried automatically.
export function useAddresses() {
  return useQuery({
    queryKey: addressKeys.list(),
    queryFn: () => addressesApi.listAddresses(),
    select: (data) => data.items.map(adaptAddress),
  });
}

function isNotFound(error: unknown): boolean {
  const apiError = error as ApiError | undefined;
  return apiError?.kind === "http" && apiError.status === 404;
}

function refetchAddresses(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: addressKeys.root });
}

// A 404 means the address is already gone server-side (deleted in another
// tab/device); refetch so the stale row disappears.
function writeOptions(queryClient: QueryClient) {
  return {
    onSuccess: () => refetchAddresses(queryClient),
    onError: (error: unknown) => {
      if (isNotFound(error)) {
        void refetchAddresses(queryClient);
      }
    },
    retry: false as const,
  };
}

export function useCreateAddress() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AddressCreateDTO) => addressesApi.createAddress(body),
    ...writeOptions(queryClient),
  });
}

export interface UpdateAddressInput {
  id: string;
  patch: AddressUpdateDTO;
}

export function useUpdateAddress() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: UpdateAddressInput) => addressesApi.updateAddress(id, patch),
    ...writeOptions(queryClient),
  });
}

export function useDeleteAddress() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => addressesApi.deleteAddress(id),
    ...writeOptions(queryClient),
  });
}

export function useSetDefaultAddress() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => addressesApi.setDefaultAddress(id),
    ...writeOptions(queryClient),
  });
}
