import { useMutation, useQueryClient } from "@tanstack/react-query";
import { notificationsApi, notificationsKeys } from "./notificationsApi";

export interface SetNotificationReadInput {
  id: string;
  read: boolean;
}

// Mark-read/unread write (confirmed: PATCH /me/notifications/{id} + CSRF,
// wired inside notificationsApi.setNotificationRead). On success,
// invalidates the whole notifications list family — simplest correct
// cache strategy; the list is small and paginated, not worth a
// per-cursor-page optimistic patch for this batch.
export function useSetNotificationRead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, read }: SetNotificationReadInput) => notificationsApi.setNotificationRead(id, read),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationsKeys.root });
    },
    retry: false,
  });
}
