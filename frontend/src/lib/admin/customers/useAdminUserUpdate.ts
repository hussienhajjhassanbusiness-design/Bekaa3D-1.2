import { useMutation, useQueryClient } from "@tanstack/react-query";
import { customersApi, customersKeys } from "./customersApi";

export function useAdminUserUpdate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ userId, isActive }: { userId: string; isActive: boolean }) =>
      customersApi.updateUserActive(userId, isActive),
    onSuccess: (_data, variables) => {
      // AGENTS.md: "Frontend should refresh authoritative data after
      // mutation" — refetch both the list (status column) and this
      // user's own detail view rather than optimistically patch either.
      void queryClient.invalidateQueries({ queryKey: customersKeys.root });
      void queryClient.invalidateQueries({ queryKey: customersKeys.detail(variables.userId) });
    },
  });
}
