"use client";

import { AdminBackLink, AdminField as Field } from "@/components/admin/adminUi";
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AdminActionDialog } from "@/components/admin/orders/AdminActionDialog";
import { InternalNoteEditor } from "@/components/admin/InternalNoteEditor";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { Alert } from "@/components/feedback/Alert";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { NotFoundContent } from "@/components/feedback/NotFoundContent";
import { Button } from "@/components/forms/Button";
import { MoneyInput } from "@/components/forms/MoneyInput";
import { describeAdminError } from "@/lib/admin/adminErrorMessages";
import {
  QUOTE_MAX_CENTS,
  QUOTE_MIN_CENTS,
  describeCustomRequestStatus,
  describeOutcome,
  getCustomRequestActions,
  isCustomRequestStatus,
  type CustomRequestAction,
} from "@/lib/admin/customRequests/customRequestPipeline";
import {
  customRequestKeys,
  customRequestsAdminApi,
  type CustomRequestAttachmentDTO,
  type CustomRequestDetailDTO,
  type CustomRequestTransitionDTO,
} from "@/lib/admin/customRequests/customRequestsAdminApi";
import type { ApiError } from "@/lib/api/ApiError";
import { formatOrderDate, formatOrderDateTime } from "@/lib/orders/orderFormat";
import { isOrderId } from "@/lib/orders/orderModel";

// #FVS-BYI-DETAIL (phase 6B-2). Visitor text (title, description,
// preferences, filenames) is rendered as plain React text, never HTML.
// Moves follow only the server's pipeline edges, each behind a
// confirmation; "Record quote" carries the amount (USD is set by the
// server). Notes save through a CSRF PATCH. Images are fetched through the
// admin session as bytes and handed to the browser as a download — never a
// URL taken from the server, never shown inline.

const QUOTE_CURRENCY_LABEL = "USD";
const NOTES_MAX = 5000;

const MESSAGES = {
  load: "Couldn't load this request. Please try again.",
  csrf: "Unable to verify your session. Please refresh the page and try again.",
  conflict: "This request has already moved on. The latest status is shown.",
  quoteRequired: "Enter the quoted amount.",
  quoteRange: "Enter an amount between $0.01 and $1,000,000.00.",
  notesTooLong: `Notes can be at most ${NOTES_MAX} characters.`,
  notesSaved: "Notes saved.",
  downloadGone: "This image has expired or is no longer available.",
};

const SIMPLE_EMAIL = /^[^\s@:/?#]+@[^\s@:/?#]+$/;

function writeError(error: unknown): string {
  const e = error as ApiError;
  if (e?.kind === "csrf" || (e?.kind === "http" && e.code === "CSRF_INVALID")) return MESSAGES.csrf;
  if (e?.kind === "http" && e.status === 409) return MESSAGES.conflict;
  if (e?.kind === "http" && e.status === 422) return MESSAGES.quoteRange;
  return describeAdminError(error);
}

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function AttachmentRow({ requestId, attachment }: { requestId: string; attachment: CustomRequestAttachmentDTO }) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function download() {
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      const { blob, filename } = await customRequestsAdminApi.downloadAttachment(requestId, attachment.id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename ?? attachment.original_filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (e) {
      const err = e as ApiError;
      setError(err?.kind === "http" && err.status === 404 ? MESSAGES.downloadGone : describeAdminError(e));
    } finally {
      setPending(false);
    }
  }

  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-outline-variant/40 py-2">
      <span className="break-all text-body-md text-on-surface">{attachment.original_filename}</span>
      <span className="text-xs text-on-surface-variant">
        {formatSize(attachment.size_bytes)} · kept until {formatOrderDate(attachment.expires_at)}
      </span>
      <Button
        type="button"
        variant="secondary"
        isLoading={pending}
        onClick={() => void download()}
        aria-label={`Download ${attachment.original_filename}`}
      >
        Download
      </Button>
      {error && (
        <p role="alert" className="w-full text-xs text-error">
          {error}
        </p>
      )}
    </li>
  );
}

export function CustomRequestView({ requestId }: { requestId: string }) {
  const validId = isOrderId(requestId);
  const queryClient = useQueryClient();
  const detail = useQuery<CustomRequestDetailDTO, ApiError>({
    queryKey: customRequestKeys.detail(requestId),
    queryFn: () => customRequestsAdminApi.getRequest(requestId),
    enabled: validId,
  });

  const [target, setTarget] = useState<CustomRequestAction | null>(null);
  const [quoteCents, setQuoteCents] = useState<number | null>(null);
  const [quoteError, setQuoteError] = useState<string | undefined>(undefined);
  const inFlight = useRef(false);
  const move = useMutation({
    mutationFn: (body: CustomRequestTransitionDTO) => customRequestsAdminApi.transition(requestId, body),
    retry: false,
  });
  const [notesStatus, setNotesStatus] = useState<{ ok: boolean; message: string } | null>(null);
  const notes = useMutation({
    mutationFn: (value: string | null) => customRequestsAdminApi.updateNotes(requestId, value),
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
  const lead = detail.data;
  if (!lead) return <NotFoundContent />;

  const { label, tone } = describeCustomRequestStatus(lead.status);
  const actions = isCustomRequestStatus(lead.status) ? getCustomRequestActions(lead.status) : [];

  function refreshLists(updated?: CustomRequestDetailDTO) {
    if (updated) queryClient.setQueryData(customRequestKeys.detail(requestId), updated);
    void queryClient.invalidateQueries({ queryKey: [...customRequestKeys.root, "list"] });
    void queryClient.invalidateQueries({ queryKey: [...customRequestKeys.root, "funnel"] });
  }

  async function confirmMove() {
    if (!target || inFlight.current) return;
    let body: CustomRequestTransitionDTO = { target_status: target.target };
    if (target.needsQuote) {
      if (quoteCents === null) {
        setQuoteError(MESSAGES.quoteRequired);
        return;
      }
      if (quoteCents < QUOTE_MIN_CENTS || quoteCents > QUOTE_MAX_CENTS) {
        setQuoteError(MESSAGES.quoteRange);
        return;
      }
      body = { ...body, quoted_amount_cents: quoteCents };
    }
    inFlight.current = true;
    try {
      const updated = await move.mutateAsync(body);
      setTarget(null);
      refreshLists(updated);
    } catch (error) {
      const e = error as ApiError;
      if (e?.kind === "http" && e.status === 409) {
        void queryClient.invalidateQueries({ queryKey: customRequestKeys.root });
      }
    } finally {
      inFlight.current = false;
    }
  }

  async function saveNotes(draft: string) {
    if (notes.isPending) return;
    setNotesStatus(null);
    if (draft.length > NOTES_MAX) {
      setNotesStatus({ ok: false, message: MESSAGES.notesTooLong });
      return;
    }
    try {
      const updated = await notes.mutateAsync(draft.trim() ? draft : null);
      refreshLists(updated);
      setNotesStatus({ ok: true, message: MESSAGES.notesSaved });
    } catch (error) {
      setNotesStatus({ ok: false, message: writeError(error) });
    }
  }

  const quote =
    lead.quoted_amount_cents !== null && lead.currency ? (
      <PriceDisplay amountCents={lead.quoted_amount_cents} currency={lead.currency} />
    ) : (
      "—"
    );

  return (
    <>
      <div>
        <AdminBackLink href="/admin/custom-requests">Bring Your Idea</AdminBackLink>
      </div>
      <h1 className="mt-2 break-words font-headline text-headline-lg text-on-surface">{lead.project_title}</h1>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <StatusBadge label={label} tone={tone} />
        <span className="text-xs text-on-surface-variant">Outcome: {describeOutcome(lead.outcome)}</span>
      </div>

      <section
        aria-labelledby="byi-requester"
        className="mt-6 flex flex-col gap-3 rounded-card border border-outline-variant/40 bg-surface-container-lowest p-5 shadow-sm tablet:p-6"
      >
        <h2 id="byi-requester" className="font-headline text-headline-md text-on-surface">
          Requester
        </h2>
        <dl className="mt-2 grid gap-3 tablet:grid-cols-3">
          <Field label="Name">{lead.name}</Field>
          <Field label="Email">
            {SIMPLE_EMAIL.test(lead.email) ? (
              <a
                href={`mailto:${lead.email}`}
                className="font-semibold text-primary underline underline-offset-2 hover:text-primary-container"
              >
                {lead.email}
              </a>
            ) : (
              lead.email
            )}
          </Field>
          <Field label="Phone">{lead.phone}</Field>
        </dl>
      </section>

      <section
        aria-labelledby="byi-idea"
        className="mt-6 flex flex-col gap-3 rounded-card border border-outline-variant/40 bg-surface-container-lowest p-5 shadow-sm tablet:p-6"
      >
        <h2 id="byi-idea" className="font-headline text-headline-md text-on-surface">
          The idea
        </h2>
        <p className="whitespace-pre-wrap break-words rounded-control bg-surface-container-low p-4 font-body text-body-md text-on-surface">
          {lead.description}
        </p>
        <dl className="mt-3 grid gap-3 tablet:grid-cols-3">
          <Field label="Preferred material">{lead.preferred_material ?? "—"}</Field>
          <Field label="Preferred colour">{lead.preferred_colour ?? "—"}</Field>
          <Field label="Dimensions">{lead.dimensions ?? "—"}</Field>
        </dl>
      </section>

      <section
        aria-labelledby="byi-images"
        className="mt-6 flex flex-col gap-3 rounded-card border border-outline-variant/40 bg-surface-container-lowest p-5 shadow-sm tablet:p-6"
      >
        <h2 id="byi-images" className="font-headline text-headline-md text-on-surface">
          Reference images
        </h2>
        {lead.attachments.length === 0 ? (
          <p className="mt-2 text-body-md text-on-surface-variant">No images, or they have expired.</p>
        ) : (
          <ul className="mt-2">
            {lead.attachments.map((attachment) => (
              <AttachmentRow key={attachment.id} requestId={lead.id} attachment={attachment} />
            ))}
          </ul>
        )}
      </section>

      <section
        aria-labelledby="byi-pipeline"
        className="mt-6 flex flex-col gap-3 rounded-card border border-outline-variant/40 bg-surface-container-lowest p-5 shadow-sm tablet:p-6"
      >
        <h2 id="byi-pipeline" className="font-headline text-headline-md text-on-surface">
          Pipeline
        </h2>
        <dl className="mt-2 grid gap-3 tablet:grid-cols-3">
          <Field label="Submitted">{formatOrderDateTime(lead.created_at)}</Field>
          <Field label="Contacted">{lead.contacted_at ? formatOrderDateTime(lead.contacted_at) : "—"}</Field>
          <Field label="Quoted">{lead.quoted_at ? formatOrderDateTime(lead.quoted_at) : "—"}</Field>
          <Field label="Quote">{quote}</Field>
          <Field label="Completed">{lead.completed_at ? formatOrderDateTime(lead.completed_at) : "—"}</Field>
          <Field label="Closed">{lead.closed_at ? formatOrderDateTime(lead.closed_at) : "—"}</Field>
        </dl>
        {actions.length > 0 ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {actions.map((action) => (
              <Button
                key={action.target}
                type="button"
                variant={action.destructive ? "secondary" : "primary"}
                onClick={() => {
                  move.reset();
                  setQuoteCents(null);
                  setQuoteError(undefined);
                  setTarget(action);
                }}
              >
                {action.label}
              </Button>
            ))}
          </div>
        ) : (
          <p className="mt-3 text-body-md text-on-surface-variant">This request is finished. No further moves.</p>
        )}
      </section>

      <section
        aria-labelledby="byi-notes"
        className="mt-6 flex flex-col gap-3 rounded-card border border-outline-variant/40 bg-surface-container-lowest p-5 shadow-sm tablet:p-6"
      >
        <h2 id="byi-notes" className="font-headline text-headline-md text-on-surface">
          Notes
        </h2>
        <div className="mt-2">
          <InternalNoteEditor
            key={lead.admin_notes ?? ""}
            note={lead.admin_notes ?? ""}
            onSave={(draft) => void saveNotes(draft)}
            isSaving={notes.isPending}
            errorMessage={notesStatus && !notesStatus.ok ? notesStatus.message : undefined}
          />
          {notesStatus?.ok && (
            <p role="status" className="mt-2 flex items-center gap-1 font-label text-label-sm uppercase text-primary">
              {notesStatus.message}
            </p>
          )}
        </div>
      </section>

      <AdminActionDialog
        open={target !== null}
        title={target ? `${target.label}?` : ""}
        description={<p>{target?.confirm}</p>}
        confirmLabel={target?.label ?? "Confirm"}
        destructive={target?.destructive ?? false}
        pending={move.isPending}
        error={move.isError ? writeError(move.error) : null}
        onConfirm={() => void confirmMove()}
        onClose={() => setTarget(null)}
      >
        {target?.needsQuote && (
          <MoneyInput
            label="Quoted amount"
            currencyLabel={QUOTE_CURRENCY_LABEL}
            valueCents={quoteCents}
            onChangeCents={(cents) => {
              setQuoteCents(cents);
              setQuoteError(undefined);
            }}
            error={quoteError}
          />
        )}
      </AdminActionDialog>
    </>
  );
}
