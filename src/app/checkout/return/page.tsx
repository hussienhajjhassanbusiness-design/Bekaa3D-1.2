import type { Metadata } from "next";
import Link from "next/link";

// Phase 5D — minimal FVS-026 -> FVS-027 handoff ONLY.
//
// The backend's payment redirect (and the mock provider's return URL) is
// {FRONTEND_BASE_URL}/checkout/return?order=<order_number> (backend
// 2dfb27b ordering/api/checkout.py create_payment_request; payments mock
// provider). Without a route here, a customer coming back from the payment
// page would land on a 404. This page deliberately reads NOTHING from the
// URL and calls no API: a return URL is never proof of payment
// (bekaa3d-commerce-ux). It says only what is true for every return: the
// payment is confirmed by the backend, not by this page. Verifying and
// showing the order's real payment state (pending/paid/failed/expired from
// GET /me/orders/{id}) is FVS-027.
//
// Phase 5E: links to /account/orders, where the order's server-backed
// status is shown. The URL carries an order number, not an id, and is still
// never read here, so the page cannot link to one order.
//
// Phase 5F (FVS-027), re-verified against backend 2dfb27b: a payment retry
// (POST /me/orders/{id}/payments) returns here too, with the same
// `?order=<order_number>`. There is still no customer lookup by order
// number (GET /me/orders filters only by status / placed_after /
// placed_before / cursor / limit), so this page stays a neutral handoff:
// it never pages through the history to find a match, never guesses an
// id, never reads the query string and never says paid or failed. The
// order page (/account/orders/{id}) is where the verified status is shown
// and re-checked.
export const metadata: Metadata = {
  title: "Payment — Bekaa3D",
};

export default function CheckoutReturnPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4 px-4 py-8 tablet:px-6">
      <h1 className="text-h1 font-bold text-text-primary">Thanks, we&apos;re confirming your payment</h1>
      <p role="status" className="rounded-md border-l-4 border-l-info bg-info-bg p-4 text-body text-text-primary">
        Your payment hasn&apos;t been confirmed yet. Check your orders for the latest status. We only treat an order as
        paid once our payment provider confirms it to us, which can take a few minutes.
      </p>
      <p className="text-body text-text-secondary">
        We&apos;ll email you and send you a notification as soon as your payment is confirmed. This page doesn&apos;t
        show your payment status; your order history shows each order&apos;s current status.
      </p>
      <div className="flex flex-wrap gap-4">
        <Link href="/account/orders" className="font-semibold text-brand-dark-green underline">
          View your orders
        </Link>
        <Link href="/account/notifications" className="font-semibold text-brand-dark-green underline">
          View notifications
        </Link>
        <Link href="/shop" className="font-semibold text-brand-dark-green underline">
          Continue shopping
        </Link>
      </div>
    </div>
  );
}
