"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { InternalNoteEditor } from "@/components/admin/InternalNoteEditor";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { governorateLabel } from "@/lib/addresses/addressModel";
import { adminOrdersApi } from "@/lib/admin/orders/adminOrdersApi";
import {
  describeAdminLineStatus,
  describeAdminRefundKind,
  describeAdminRefundStatus,
  describeCancelReason,
  describePaymentProvider,
} from "@/lib/admin/orders/adminOrderPresentation";
import type { AdminOrderDetailDTO, AdminOrderLineReadDTO } from "@/lib/admin/orders/adminOrderTypes";
import { useAdminOrderWrite } from "@/lib/admin/orders/useAdminOrders";
import type { PriceRead } from "@/lib/catalog/productTypes";
import { formatOrderDate, formatOrderDateTime, fulfillmentLabel, paymentMethodLabel } from "@/lib/orders/orderFormat";
import { describeOrderStatus, describePaymentStatus } from "@/lib/orders/orderStatus";
import { CreateChargeback } from "@/components/admin/payments/CreateChargeback";
import { CreateRefund } from "@/components/admin/payments/CreateRefund";
import { LineActions } from "./LineActions";
import { OrderLevelActions } from "./OrderLevelActions";

// #FVS030-ADMIN-ORDER-VIEW (phase 5H)
//
// GET /api/v1/admin/orders/{id}, rendered as the server has it: real line
// states, each line's server-provided actions, payments (linked to their
// admin payment page), refunds (Record a refund, phase 5I; rows linked to
// the refund page) and chargebacks (Record a chargeback, phase 6A; a
// recorded one is read-only: no update route exists), the full
// history with who did each step, and the internal note (PATCH). No
// shipping fee (ADR-024), no STL file handling (ADR-019).
export function AdminOrderView({ order }: { order: AdminOrderDetailDTO }) {
  const status = describeOrderStatus(order.status);
  const lineName = new Map(order.lines.map((line) => [line.id, line.name]));

  return (
    <article aria-labelledby="admin-order-heading" className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <Link href="/admin/orders" className="self-start text-body text-text-link underline">
          Back to orders
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 id="admin-order-heading" className="text-h1 font-bold text-text-primary">
            Order {order.order_number}
          </h1>
          <StatusBadge label={status.label} tone={status.tone} />
        </div>
        <p className="text-body text-text-secondary">
          Placed {formatOrderDateTime(order.placed_at)} by {order.customer_email}
          {order.source === "offer" ? " · from an accepted offer" : ""}
        </p>
      </header>

      <OrderLevelActions order={order} />

      <div className="flex flex-col gap-6 desktop:flex-row desktop:items-start">
        <div className="flex min-w-0 flex-1 flex-col gap-6">
          <Section title="Items">
            <ul className="flex flex-col divide-y divide-border-default">
              {order.lines.map((line) => (
                <li key={line.id} className="flex flex-col gap-2 py-3">
                  <LineRow line={line} />
                  <LineActions orderId={order.id} line={line} />
                </li>
              ))}
            </ul>
          </Section>

          <Fulfillment order={order} />

          <Section title="History">
            <ol className="flex flex-col gap-2">
              {order.status_history.map((entry, index) => {
                const label = entry.order_item_id === null ? "Order" : (lineName.get(entry.order_item_id) ?? "An item");
                const product = order.lines.find((l) => l.id === entry.order_item_id)?.product_type ?? "physical";
                const to =
                  entry.order_item_id === null
                    ? describeOrderStatus(entry.to_status).label
                    : describeAdminLineStatus(entry.to_status, product).label;
                const who =
                  entry.actor_user_id === null ? "System" : entry.actor_user_id === order.customer_id ? "Customer" : "Staff";
                return (
                  <li key={`${entry.at}-${index}`} className="text-body text-text-primary">
                    <span className="font-semibold">{label}:</span> {to}
                    <span className="block text-caption text-text-secondary">
                      {formatOrderDateTime(entry.at)} · {who}
                    </span>
                    {entry.reason && <span className="block whitespace-pre-line text-caption text-text-secondary">“{entry.reason}”</span>}
                  </li>
                );
              })}
            </ol>
          </Section>
        </div>

        <div className="flex flex-col gap-6 desktop:w-96 desktop:shrink-0">
          <Section title="Payment">
            <dl className="flex flex-col gap-2 text-body">
              <Row label="Method">{paymentMethodLabel(order.payment_method)}</Row>
              <Row label="Subtotal">
                <Amount price={order.subtotal} />
              </Row>
              <Row label="Tax">
                <Amount price={order.tax} />
              </Row>
              <Row label="Total">
                <Amount price={order.total} />
              </Row>
              {order.payment_due && order.amount_due && (
                <Row label="Cash due">
                  <Amount price={order.amount_due} />
                </Row>
              )}
            </dl>
            {order.payments.length === 0 ? (
              <p className="text-caption text-text-secondary">No payment recorded yet.</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {order.payments.map((p) => {
                  const d = describePaymentStatus(p.status);
                  return (
                    <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 text-body">
                      <span>
                        <Link href={`/admin/payments/${p.id}`} className="text-text-link underline">
                          Payment
                        </Link>{" "}
                        <StatusBadge label={d.label} tone={d.tone} />{" "}
                        <span className="text-caption text-text-secondary">
                          {describePaymentProvider(p.provider)} · {formatOrderDateTime(p.initiated_at)}
                        </span>
                      </span>
                      <Amount price={p.amount} />
                    </li>
                  );
                })}
              </ul>
            )}
          </Section>

          {((order.refunds ?? []).length > 0 || order.payment_reached_paid) && (
            <Section title="Refunds">
              <CreateRefund order={order} />
              <ul className="flex flex-col gap-2">
                {(order.refunds ?? []).map((r) => {
                  const d = describeAdminRefundStatus(r.status);
                  return (
                    <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 text-body">
                      <span>
                        <Link href={`/admin/refunds/${r.id}`} className="text-text-link underline">
                          {describeAdminRefundKind(r.kind)}
                        </Link>{" "}
                        <StatusBadge label={d.label} tone={d.tone} />
                        <span className="block text-caption text-text-secondary">{formatOrderDate(r.created_at)}</span>
                      </span>
                      <Amount price={r.amount} />
                    </li>
                  );
                })}
              </ul>
            </Section>
          )}

          {((order.chargebacks ?? []).length > 0 || (order.payment_reached_paid && order.payment_method === "online")) && (
            <Section title="Chargebacks">
              <CreateChargeback order={order} />
              <ul className="flex flex-col gap-2">
                {(order.chargebacks ?? []).map((c) => (
                  <li key={c.id} className="flex flex-wrap justify-between gap-2 text-body">
                    <span className="text-caption text-text-secondary">Received {formatOrderDate(c.received_at)}</span>
                    <Amount price={c.charged} />
                  </li>
                ))}
              </ul>
            </Section>
          )}

          <AdminNote order={order} />
        </div>
      </div>
    </article>
  );
}

function AdminNote({ order }: { order: AdminOrderDetailDTO }) {
  const write = useAdminOrderWrite();
  return (
    <Section title="Internal note">
      {/* Remounts when the server's note changes, so a saved or refetched
          value replaces the draft, while an unsaved edit survives other refetches. */}
      <InternalNoteEditor
        key={order.admin_note ?? ""}
        note={order.admin_note ?? ""}
        isSaving={write.state.kind === "pending"}
        errorMessage={write.state.kind === "error" ? write.state.message : undefined}
        onSave={(draft) => void write.run(() => adminOrdersApi.updateNote(order.id, { admin_note: draft.trim() ? draft : null }))}
      />
    </Section>
  );
}

function LineRow({ line }: { line: AdminOrderLineReadDTO }) {
  const s = describeAdminLineStatus(line.fulfillment_status, line.product_type);
  return (
    <div className="flex flex-col gap-1 tablet:flex-row tablet:items-start tablet:justify-between">
      <div className="min-w-0">
        <p className="font-semibold text-text-primary">{line.name}</p>
        <p className="text-caption text-text-secondary">
          {line.product_type === "stl" ? "STL file (emailed by hand)" : "Printed item"} · Qty {line.quantity} ×{" "}
          <Amount price={line.unit_price} />
        </p>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <StatusBadge label={s.label} tone={s.tone} />
          {line.cancel_reason && <span className="text-caption text-text-secondary">{describeCancelReason(line.cancel_reason)}</span>}
          {line.fulfilled_at && line.product_type === "stl" && (
            <span className="text-caption text-text-secondary">Emailed {formatOrderDate(line.fulfilled_at)}</span>
          )}
          {line.receipt_confirmed_at && (
            <span className="text-caption text-text-secondary">Customer confirmed receipt {formatOrderDate(line.receipt_confirmed_at)}</span>
          )}
          {line.problem_reported_at && (
            <span className="text-caption text-danger">Problem reported {formatOrderDate(line.problem_reported_at)}</span>
          )}
        </div>
      </div>
      <Amount price={line.line_total} />
    </div>
  );
}

function Fulfillment({ order }: { order: AdminOrderDetailDTO }) {
  const a = order.delivery_address;
  const place = a ? [a.street, a.area, a.city, a.governorate ? governorateLabel(a.governorate) : null].filter(Boolean).join(", ") : "";
  return (
    <Section title="Fulfillment">
      <dl className="flex flex-col gap-2 text-body">
        <Row label="Method">{fulfillmentLabel(order.fulfillment_method)}</Row>
        {a && (
          <Row label="Deliver to">
            <span className="text-right">
              {a.recipient_name && <span className="block">{a.recipient_name}</span>}
              {place && <span className="block">{place}</span>}
              {a.landmark_notes && <span className="block text-text-secondary">{a.landmark_notes}</span>}
            </span>
          </Row>
        )}
        {order.contact_phone && <Row label="Contact phone">{order.contact_phone}</Row>}
        {order.estimated_dispatch_at && <Row label="Estimated ready">{formatOrderDate(order.estimated_dispatch_at)}</Row>}
      </dl>
      {order.delivery_fee_note && (
        <p className="text-caption text-text-secondary">The courier sets and collects the delivery fee separately.</p>
      )}
      {order.customer_note && (
        <div>
          <p className="text-label font-semibold uppercase tracking-label text-text-secondary">Customer note</p>
          <p className="whitespace-pre-line text-body text-text-primary">{order.customer_note}</p>
        </div>
      )}
    </Section>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="flex flex-col gap-3 rounded-md border border-border-default bg-white p-4">
      <h2 className="text-h3 font-bold text-text-primary">{title}</h2>
      {children}
    </section>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-text-secondary">{label}</dt>
      <dd className="text-text-primary">{children}</dd>
    </div>
  );
}

function Amount({ price }: { price: PriceRead }) {
  return <PriceDisplay amountCents={price.amount_cents} currency={price.currency} />;
}
