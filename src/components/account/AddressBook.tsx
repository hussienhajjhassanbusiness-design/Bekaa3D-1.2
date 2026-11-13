"use client";

import { useId, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/forms/Button";
import { Alert } from "@/components/feedback/Alert";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { DialogShell } from "@/components/feedback/DialogShell";
import { AddressList } from "./AddressList";
import { AddressForm } from "./AddressForm";
import { useAuth } from "@/lib/auth/AuthProvider";
import {
  useAddresses,
  useCreateAddress,
  useDeleteAddress,
  useSetDefaultAddress,
  useUpdateAddress,
} from "@/lib/addresses/useAddresses";
import {
  addressFormDefaults,
  buildAddressCreatePayload,
  buildAddressUpdatePayload,
  type AddressFormValues,
} from "@/lib/addresses/addressPayloads";
import { ADDRESS_MESSAGES, describeAddressWriteError } from "@/lib/addresses/addressErrors";
import type { AddressModel } from "@/lib/addresses/addressModel";
import type { FieldValidationError } from "@/lib/api/validationErrors";

type EditorState = { mode: "create" } | { mode: "edit"; address: AddressModel } | null;

const DIALOG_PANEL_CLASSNAME =
  "w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-card border border-outline-variant/30 bg-surface-container-lowest p-4 shadow-2xl tablet:p-6";

// #FVS023-ADDRESS-BOOK — /account/addresses, against the real backend
// (VS-026). Every write ends in a refetch of the list (useAddresses.ts),
// so what is shown is always the server's state: the default badge moves
// only after the server says so, and deleting the default shows "no
// default" because the backend promotes nothing (VS-026 Q5).
// Error copy is frontend-owned (addressErrors.ts); Problem.detail and
// ValidationError.msg never reach the page.
// ADR-024: an address is contact/delivery information — no zone, no
// shipping price, no free-shipping threshold anywhere here.
export function AddressBook() {
  const { user } = useAuth();
  const query = useAddresses();
  const createAddress = useCreateAddress();
  const updateAddress = useUpdateAddress();
  const deleteAddress = useDeleteAddress();
  const setDefaultAddress = useSetDefaultAddress();

  const [editor, setEditor] = useState<EditorState>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AddressModel | null>(null);
  const [pendingDefaultId, setPendingDefaultId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);
  const editorTitleId = useId();

  const addresses = query.data ?? [];
  const findAddress = (id: string) => addresses.find((address) => address.id === id);

  function openEditor(next: EditorState) {
    setFormError(null);
    setPageError(null);
    setNotice(null);
    setEditor(next);
  }

  function closeEditor() {
    setEditor(null);
    setFormError(null);
  }

  // Resolves with field errors for the form to show; otherwise handles
  // the outcome here.
  async function handleSubmit(values: AddressFormValues): Promise<FieldValidationError[] | void> {
    if (!editor) {
      return;
    }
    setFormError(null);

    if (editor.mode === "edit") {
      const patch = buildAddressUpdatePayload(editor.address, values);
      if (Object.keys(patch).length === 0) {
        closeEditor();
        setNotice("No changes to save.");
        return;
      }
      try {
        await updateAddress.mutateAsync({ id: editor.address.id, patch });
        closeEditor();
        setNotice("Address updated.");
      } catch (error) {
        return handleEditorError(error);
      }
      return;
    }

    try {
      await createAddress.mutateAsync(buildAddressCreatePayload(values));
      closeEditor();
      setNotice("Address saved.");
    } catch (error) {
      return handleEditorError(error);
    }
  }

  function handleEditorError(error: unknown): FieldValidationError[] {
    const description = describeAddressWriteError(error);
    if (description.notFound) {
      // Edited an address that was deleted elsewhere; the list refetches.
      closeEditor();
      setPageError(description.formMessage);
      return [];
    }
    setFormError(description.formMessage);
    return description.fieldErrors;
  }

  async function handleConfirmDelete() {
    if (!deleteTarget) {
      return;
    }
    setPageError(null);
    setNotice(null);
    try {
      await deleteAddress.mutateAsync(deleteTarget.id);
      setNotice("Address deleted.");
    } catch (error) {
      setPageError(describeAddressWriteError(error).formMessage);
    } finally {
      setDeleteTarget(null);
    }
  }

  async function handleSetDefault(id: string) {
    setPageError(null);
    setNotice(null);
    setPendingDefaultId(id);
    try {
      await setDefaultAddress.mutateAsync(id);
      setNotice("Default address updated.");
    } catch (error) {
      setPageError(describeAddressWriteError(error).formMessage);
    } finally {
      setPendingDefaultId(null);
    }
  }

  const isEditing = editor?.mode === "edit";
  const hasAddresses = query.isSuccess && addresses.length > 0;
  const deleteDescription = deleteTarget
    ? `“${deleteTarget.label}” will be removed from your address book. Orders you've already placed keep their own delivery details.` +
      (deleteTarget.isDefault ? " This is your default address — after deleting it you won't have a default address until you choose one." : "")
    : "";

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-h1 font-bold text-text-primary">Addresses</h1>
        {hasAddresses && (
          <Button type="button" onClick={() => openEditor({ mode: "create" })}>
            Add address
          </Button>
        )}
      </div>
      <p className="mt-1 text-body text-text-secondary">Saved delivery addresses you can choose at checkout.</p>

      {user && !user.emailVerified && (
        <div className="mt-4 flex flex-col gap-2">
          <Alert variant="warning" message={ADDRESS_MESSAGES.verifyEmail} />
          <Link href="/verify-email/resend" className="text-body text-brand-dark-green underline">
            Resend the verification email
          </Link>
        </div>
      )}

      <div className="mt-4 flex flex-col gap-2" aria-live="polite">
        {notice && <Alert variant="success" message={notice} />}
      </div>
      {pageError && (
        <div className="mt-2">
          <Alert variant="error" message={pageError} />
        </div>
      )}

      <div className="mt-4">
        <AddressList
          addresses={addresses}
          isLoading={query.isLoading}
          isError={query.isError}
          onRetry={() => query.refetch()}
          onAdd={() => openEditor({ mode: "create" })}
          onEdit={(id) => {
            const address = findAddress(id);
            if (address) {
              openEditor({ mode: "edit", address });
            }
          }}
          onDelete={(id) => {
            setNotice(null);
            setPageError(null);
            setDeleteTarget(findAddress(id) ?? null);
          }}
          onSetDefault={handleSetDefault}
          pendingDefaultId={pendingDefaultId}
        />
      </div>

      <DialogShell
        open={editor !== null}
        onClose={closeEditor}
        isBusy={createAddress.isPending || updateAddress.isPending}
        labelledBy={editorTitleId}
        panelClassName={DIALOG_PANEL_CLASSNAME}
      >
        <h2 id={editorTitleId} className="mb-4 text-h3 font-bold text-text-primary">
          {isEditing ? "Edit address" : "Add address"}
        </h2>
        {editor && (
          <AddressForm
            key={isEditing ? editor.address.id : "create"}
            initialValues={addressFormDefaults(isEditing ? editor.address : undefined)}
            submitLabel={isEditing ? "Save changes" : "Save address"}
            onSubmit={handleSubmit}
            onCancel={closeEditor}
            formError={formError}
            defaultIsAutomatic={!isEditing && addresses.length === 0}
          />
        )}
      </DialogShell>

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete address"
        description={deleteDescription}
        confirmLabel="Delete address"
        isDestructive
        isConfirming={deleteAddress.isPending}
        onConfirm={handleConfirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </>
  );
}
