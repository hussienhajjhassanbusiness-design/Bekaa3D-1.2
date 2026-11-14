"use client";

import { Suspense, useState, type FormEvent } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AdminActionDialog } from "@/components/admin/orders/AdminActionDialog";
import { AdminTable, type AdminTableColumn } from "@/components/admin/AdminTable";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { Alert } from "@/components/feedback/Alert";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { Button } from "@/components/forms/Button";
import { SelectField } from "@/components/forms/SelectField";
import { TextField } from "@/components/forms/TextField";
import { describeAdminError } from "@/lib/admin/adminErrorMessages";
import {
  cashBlockKeys,
  cashBlocksApi,
  type CashPaymentBlockPageDTO,
  type CashPaymentBlockReadDTO,
} from "@/lib/admin/cashBlocks/cashBlocksApi";
import { describeCancelReason } from "@/lib/admin/orders/adminOrderPresentation";
import { adminOrderKeys } from "@/lib/admin/orders/adminOrdersApi";
import { useCursorPagination } from "@/lib/admin/useCursorPagination";
import type { ApiError } from "@/lib/api/ApiError";
import { formatOrderDateTime } from "@/lib/orders/orderFormat";
import { isOrderId } from "@/lib/orders/orderModel";

// FVS (phase 6A) — /admin/cash-blocks. Blocks are created by the server
// when a cash order ends refused / not collected; an administrator only
// lists, searches (by phone, in a POST body, never in the URL or a query
// key) and clears them. `?customer_id=` (from the customer page) narrows the
// list. Clearing a cleared block changes nothing server-side.

const MESSAGES = {
  phone: "Enter a valid Lebanese phone number.",
  csrf: "Unable to verify your session. Please refresh the page and try again.",
};

function searchError(error: unknown): string {
  const e = error as ApiError;
  if (e?.kind === "http" && e.status === 422) return MESSAGES.phone;
  if (e?.kind === "csrf" || (e?.kind === "http" && e.code === "CSRF_INVALID")) return MESSAGES.csrf;
  return describeAdminError(error);
}

function AdminCashBlocksPageContent() {
  const params = useSearchParams();
  const customerParam = params.get("customer_id");
  const customerId = customerParam && isOrderId(customerParam) ? customerParam : undefined;
  const [active, setActive] = useState<boolean | undefined>(true);
  const pagination = useCursorPagination(JSON.stringify({ active, customerId }));
  const queryClient = useQueryClient();

  const list = useQuery<CashPaymentBlockPageDTO, ApiError>({
    queryKey: cashBlockKeys.list({ active, customer_id: customerId, cursor: pagination.cursor }),
    queryFn: () => cashBlocksApi.listBlocks({ active, customer_id: customerId, cursor: pagination.cursor }),
  });

  // Phone search: a mutation (a POST), so the number is never cached under a key.
  const [phone, setPhone] = useState("");
  const search = useMutation({
    mutationFn: (p: string) => cashBlocksApi.searchBlocks({ phone: p, active }),
    retry: false,
  });

  const [target, setTarget] = useState<CashPaymentBlockReadDTO | null>(null);
  const clear = useMutation({ mutationFn: (id: string) => cashBlocksApi.clearBlock(id), retry: false });

  async function confirmClear() {
    if (!target || clear.isPending) return;
    try {
      await clear.mutateAsync(target.id);
      setTarget(null);
      search.reset();
      void queryClient.invalidateQueries({ queryKey: cashBlockKeys.root });
      void queryClient.invalidateQueries({ queryKey: adminOrderKeys.root });
    } catch {
      void queryClient.invalidateQueries({ queryKey: cashBlockKeys.root });
    }
  }

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (phone.trim()) search.mutate(phone.trim());
  }

  const rows = search.data?.items ?? list.data?.items ?? [];
  const columns: readonly AdminTableColumn<CashPaymentBlockReadDTO>[] = [
    {
      header: "Order",
      render: (r) => (
        <Link
          href={`/admin/orders/${r.order_id}`}
          className="font-semibold text-primary underline underline-offset-2 hover:text-primary-container"
        >
          {r.order_number}
        </Link>
      ),
    },
    { header: "Reason", render: (r) => describeCancelReason(r.reason) },
    {
      header: "Status",
      render: (r) => <StatusBadge label={r.active ? "Active" : "Cleared"} tone={r.active ? "warning" : "neutral"} />,
    },
    { header: "Blocked", render: (r) => formatOrderDateTime(r.created_at) },
    { header: "Cleared", render: (r) => (r.cleared_at ? formatOrderDateTime(r.cleared_at) : "—") },
  ];

  return (
    <>
      <h1 className="break-words font-headline text-headline-lg text-on-surface">Cash blocks</h1>
      <p className="mt-2 max-w-3xl font-body text-body-md text-on-surface-variant">
        A block is added automatically when a cash order is refused or not collected. It keeps that customer and phone
        from paying cash until you clear it. It doesn&apos;t deactivate the account.
      </p>
      {customerId && (
        <p className="mt-4 rounded-control border border-info-outline bg-info-container px-4 py-3 font-body text-body-md text-on-info-container">
          Showing one customer&apos;s blocks.{" "}
          <Link
            href="/admin/cash-blocks"
            className="font-semibold text-primary underline underline-offset-2 hover:text-primary-container"
          >
            Show all
          </Link>
        </p>
      )}
      <div className="mt-6 grid gap-4 rounded-card border border-outline-variant/40 bg-surface-container-lowest p-4 shadow-sm tablet:p-6 tablet:grid-cols-2">
        <SelectField
          label="Show"
          value={active === undefined ? "" : String(active)}
          onChange={(e) => setActive(e.target.value === "" ? undefined : e.target.value === "true")}
        >
          <option value="true">Active blocks</option>
          <option value="false">Cleared blocks</option>
          <option value="">All blocks</option>
        </SelectField>
        <form onSubmit={submitSearch} className="flex flex-wrap items-end gap-3" noValidate>
          <div className="w-full sm:w-auto sm:flex-1">
            <TextField
              label="Find by contact phone"
              type="tel"
              autoComplete="off"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
            />
          </div>
          <Button type="submit" isLoading={search.isPending}>
            Search
          </Button>
          {search.data && (
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                search.reset();
                setPhone("");
              }}
            >
              Clear search
            </Button>
          )}
        </form>
      </div>
      {search.isError && (
        <div className="mt-4">
          <Alert variant="error" message={searchError(search.error)} />
        </div>
      )}
      {list.isError && !search.data && (
        <div className="mt-4">
          <Alert variant="error" message={describeAdminError(list.error)} />
        </div>
      )}
      <div className="mt-6">
        <AdminTable
          columns={columns}
          rows={rows}
          getRowKey={(r) => r.id}
          isLoading={list.isLoading && !search.data}
          emptyMessage={search.data ? "No blocks for that phone." : "No cash blocks."}
          hasPrevious={!search.data && pagination.hasPrevious}
          hasNext={!search.data && list.data?.next_cursor != null}
          onPrevious={pagination.goPrevious}
          onNext={() => {
            if (list.data?.next_cursor) pagination.goNext(list.data.next_cursor);
          }}
          rowActions={(r) =>
            r.active ? (
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  clear.reset();
                  setTarget(r);
                }}
              >
                Clear block
              </Button>
            ) : null
          }
        />
      </div>
      <AdminActionDialog
        open={target !== null}
        title="Clear this cash block?"
        description={<p>The customer and phone from order {target?.order_number} can pay cash again.</p>}
        confirmLabel="Clear block"
        pending={clear.isPending}
        error={clear.isError ? searchError(clear.error) : null}
        onConfirm={() => void confirmClear()}
        onClose={() => setTarget(null)}
      />
    </>
  );
}

// useSearchParams() needs a Suspense boundary to keep the page prerenderable
// (Next.js App Router; same convention as /login).
export default function AdminCashBlocksPage() {
  return (
    <Suspense fallback={<LoadingSpinner />}>
      <AdminCashBlocksPageContent />
    </Suspense>
  );
}
