"use client";

import { useMemo, useState } from "react";
import { NotificationList } from "@/components/notifications/NotificationList";
import { Alert } from "@/components/feedback/Alert";
import { useNotifications } from "@/lib/notifications/useNotifications";
import { useSetNotificationRead } from "@/lib/notifications/useSetNotificationRead";
import { adaptNotification } from "@/lib/notifications/notificationAdapter";
import type { ApiError } from "@/lib/api/ApiError";

// Phase 2 auth/account batch (FVS-008) — AccountLayout (mounted via
// src/app/account/layout.tsx) already supplies the ProtectedRoute
// boundary, nav, and content landmark; this page renders only the real
// content, wired to the real confirmed contract (GET/PATCH
// /me/notifications). No unread-count endpoint exists — this page never
// fabricates a total unread count; the header bell badge stays unmounted
// (a deliberate, documented scope decision, not an oversight).
const LIST_ERROR_MESSAGE = "We couldn't load your notifications. Please try again.";
const VERIFY_EMAIL_MESSAGE = "Verify your email to manage notifications.";
const CSRF_MESSAGE = "Unable to verify your session. Please refresh the page and try again.";
const GENERIC_WRITE_FAILURE_MESSAGE = "Something went wrong. Please try again.";

function isRecognizedApiError(value: unknown): value is ApiError {
  return typeof value === "object" && value !== null && "kind" in value;
}

// §error contract — branch on `code`, never on title/detail text; the
// backend's own diagnostic string is never shown verbatim.
function writeFailureMessage(error: unknown): string {
  if (isRecognizedApiError(error) && error.kind === "http") {
    if (error.code === "EMAIL_VERIFICATION_REQUIRED") {
      return VERIFY_EMAIL_MESSAGE;
    }
    if (error.code === "CSRF_INVALID") {
      return CSRF_MESSAGE;
    }
  }
  return GENERIC_WRITE_FAILURE_MESSAGE;
}

export default function AccountNotificationsPage() {
  const query = useNotifications({});
  const setRead = useSetNotificationRead();
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [writeFailure, setWriteFailure] = useState<string | null>(null);

  const notifications = useMemo(
    () => (query.data?.pages ?? []).flatMap((page) => page.items).map(adaptNotification),
    [query.data]
  );

  async function handleToggleRead(id: string, nextIsRead: boolean) {
    setWriteFailure(null);
    setPendingId(id);
    try {
      await setRead.mutateAsync({ id, read: nextIsRead });
    } catch (error) {
      setWriteFailure(writeFailureMessage(error));
    } finally {
      setPendingId(null);
    }
  }

  return (
    <>
      <h1 className="text-h1 font-bold text-text-primary">Notifications</h1>
      {writeFailure && <Alert variant="error" message={writeFailure} />}
      <div className="mt-4">
        <NotificationList
          notifications={notifications}
          onToggleRead={handleToggleRead}
          isLoading={query.isLoading}
          isError={query.isError}
          errorMessage={LIST_ERROR_MESSAGE}
          onRetry={() => query.refetch()}
          pendingId={pendingId}
          canLoadMore={query.hasNextPage}
          isLoadingMore={query.isFetchingNextPage}
          onLoadMore={() => query.fetchNextPage()}
        />
      </div>
    </>
  );
}
