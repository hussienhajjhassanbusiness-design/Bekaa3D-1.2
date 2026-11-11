"use client";

import { useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AdminActionDialog } from "@/components/admin/orders/AdminActionDialog";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { Alert } from "@/components/feedback/Alert";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { NotFoundContent } from "@/components/feedback/NotFoundContent";
import { Button } from "@/components/forms/Button";
import { describeAdminError } from "@/lib/admin/adminErrorMessages";
import {
  describeContactMessageStatus,
  getContactMessageActions,
  isContactMessageStatus,
  type ContactMessageAction,
} from "@/lib/admin/contactMessageWorkflow";
import {
  contactMessageKeys,
  contactMessagesAdminApi,
  type ContactMessageDTO,
} from "@/lib/admin/contactMessages/contactMessagesAdminApi";
import type { ApiError } from "@/lib/api/ApiError";
import { formatOrderDateTime } from "@/lib/orders/orderFormat";
import { isOrderId } from "@/lib/orders/orderModel";

// #FVS-CONTACT-DETAIL (phase 6B-1). Visitor text is rendered as plain React
// text (pre-wrap), never as HTML. Status moves are forward only (skips
// allowed) and cannot be undone, so each goes through a confirmation; the
// PATCH carries the CSRF header. A 409 (someone else moved it) refetches.

const MESSAGES = {
  load: "Couldn't load this message. Please try again.",
  csrf: "Unable to verify your session. Please refresh the page and try again.",
  conflict: "This message has already moved on. The latest status is shown.",
};

// Only a plain address becomes a mailto: link (the server validated it as an
// email, this is defence in depth against an odd value becoming a URL).
const SIMPLE_EMAIL = /^[^\s@:/?#]+@[^\s@:/?#]+$/;

function statusError(error: unknown): string {
  const e = error as ApiError;
  if (e?.kind === "csrf" || (e?.kind === "http" && e.code === "CSRF_INVALID")) return MESSAGES.csrf;
  if (e?.kind === "http" && e.status === 409) return MESSAGES.conflict;
  return describeAdminError(error);
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-label font-semibold uppercase tracking-label text-text-secondary">{label}</dt>
      <dd className="mt-1 break-words text-body text-text-primary">{children}</dd>
    </div>
  );
}

export function ContactMessageView({ messageId }: { messageId: string }) {
  const validId = isOrderId(messageId);
  const queryClient = useQueryClient();
  const detail = useQuery<ContactMessageDTO, ApiError>({
    queryKey: contactMessageKeys.detail(messageId),
    queryFn: () => contactMessagesAdminApi.getMessage(messageId),
    enabled: validId,
  });
  const [target, setTarget] = useState<ContactMessageAction | null>(null);
  // Synchronous double-submit guard (isPending only flips on the next render).
  const inFlight = useRef(false);
  const update = useMutation({
    mutationFn: (action: ContactMessageAction) => contactMessagesAdminApi.updateStatus(messageId, action.nextStatus),
    retry: false,
  });

  if (!validId) return <NotFoundContent />;
  if (detail.isLoading) return <LoadingSpinner />;
  if (detail.isError) {
    return detail.error?.kind === "http" && detail.error.status === 404 ? (
      <NotFoundContent />
    ) : (
      <Alert variant="error" message={MESSAGES.load} />
    );
  }
  const message = detail.data;
  if (!message) return <NotFoundContent />;

  const { label, tone } = describeContactMessageStatus(message.status);
  const actions = isContactMessageStatus(message.status) ? getContactMessageActions(message.status) : [];

  async function confirm() {
    if (!target || inFlight.current) return;
    inFlight.current = true;
    try {
      const updated = await update.mutateAsync(target);
      queryClient.setQueryData(contactMessageKeys.detail(messageId), updated);
      setTarget(null);
      void queryClient.invalidateQueries({ queryKey: [...contactMessageKeys.root, "list"] });
    } catch (error) {
      const e = error as ApiError;
      if (e?.kind === "http" && e.status === 409) {
        void queryClient.invalidateQueries({ queryKey: contactMessageKeys.root });
      }
    } finally {
      inFlight.current = false;
    }
  }

  return (
    <>
      <p>
        <Link href="/admin/contact-messages" className="text-text-link underline">
          ← Contact messages
        </Link>
      </p>
      <h1 className="mt-2 break-words text-h1 font-bold text-text-primary">{message.subject ?? "No subject"}</h1>
      <div className="mt-2">
        <StatusBadge label={label} tone={tone} />
      </div>

      <dl className="mt-4 grid gap-3 tablet:grid-cols-2">
        <Field label="From">{message.name}</Field>
        <Field label="Email">
          {SIMPLE_EMAIL.test(message.email) ? (
            <a href={`mailto:${message.email}`} className="text-text-link underline">
              {message.email}
            </a>
          ) : (
            message.email
          )}
        </Field>
        <Field label="Phone">{message.phone ?? "—"}</Field>
        <Field label="Received">{formatOrderDateTime(message.created_at)}</Field>
        <Field label="Last updated">{formatOrderDateTime(message.updated_at)}</Field>
        {message.order_id && (
          <Field label="Order problem report">
            <Link href={`/admin/orders/${encodeURIComponent(message.order_id)}`} className="text-text-link underline">
              View order
            </Link>
            {message.user_id && (
              <>
                {" · "}
                <Link href={`/admin/customers/${encodeURIComponent(message.user_id)}`} className="text-text-link underline">
                  View customer
                </Link>
              </>
            )}
          </Field>
        )}
      </dl>

      <section aria-labelledby="contact-message-body" className="mt-6">
        <h2 id="contact-message-body" className="text-h3 font-semibold text-text-primary">
          Message
        </h2>
        <p className="mt-2 whitespace-pre-wrap break-words rounded-md border border-border-default p-4 text-body text-text-primary">
          {message.message}
        </p>
      </section>

      {actions.length > 0 && (
        <section aria-labelledby="contact-message-actions" className="mt-6">
          <h2 id="contact-message-actions" className="text-h3 font-semibold text-text-primary">
            Status
          </h2>
          <p className="mt-1 text-caption text-text-secondary">Status only moves forward and can&apos;t be undone.</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {actions.map((action, index) => (
              <Button
                key={action.nextStatus}
                type="button"
                variant={index === 0 ? "primary" : "secondary"}
                onClick={() => {
                  update.reset();
                  setTarget(action);
                }}
              >
                {action.label}
              </Button>
            ))}
          </div>
        </section>
      )}

      <AdminActionDialog
        open={target !== null}
        title={target ? `${target.label}?` : ""}
        description={
          <p>
            The message becomes “{target ? describeContactMessageStatus(target.nextStatus).label : ""}”. It can&apos;t be moved
            back.
          </p>
        }
        confirmLabel={target?.label ?? "Confirm"}
        pending={update.isPending}
        error={update.isError ? statusError(update.error) : null}
        onConfirm={() => void confirm()}
        onClose={() => setTarget(null)}
      />
    </>
  );
}
