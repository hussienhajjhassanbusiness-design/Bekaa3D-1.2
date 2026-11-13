import type { Metadata } from "next";
import Link from "next/link";
import { buttonLinkClassName } from "@/components/forms/Button";
import { Container } from "@/components/ui/Container";
import { Icon } from "@/components/ui/Icon";

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

// Batch 7 (DERIVED from the Batch 6 checkout result card + §48 result
// overlay card): a centred white card with a neutral "pending" glyph (the
// open-in-new / schedule language, never a success check or an error
// mark), the same copy, and the same three links — "View your orders" as
// the one primary action. Still reads nothing and claims no outcome.
export default function CheckoutReturnPage() {
  return (
    <Container className="py-12 tablet:py-16">
      <div className="mx-auto flex max-w-2xl flex-col items-center gap-6 rounded-panel border border-outline-variant/30 bg-surface-container-lowest p-6 text-center shadow-sm tablet:p-12">
        <div
          aria-hidden="true"
          className="flex h-20 w-20 items-center justify-center rounded-full bg-info-container text-on-info-container"
        >
          <Icon name="schedule" className="h-10 w-10" strokeWidth={1.5} />
        </div>
        <div className="flex flex-col gap-2">
          <p className="font-label text-label-caps uppercase tracking-widest text-on-surface-variant">Payment</p>
          <h1 className="font-headline text-headline-lg text-on-surface">Thanks, we&apos;re confirming your payment</h1>
        </div>
        <p
          role="status"
          className="flex items-start gap-3 rounded-card border border-info-outline bg-info-container p-4 text-left text-body-md text-on-info-container"
        >
          <Icon name="info" className="mt-0.5 h-5 w-5 shrink-0 text-info" />
          <span className="min-w-0">
            Your payment hasn&apos;t been confirmed yet. Check your orders for the latest status. We only treat an order
            as paid once our payment provider confirms it to us, which can take a few minutes.
          </span>
        </p>
        <p className="text-body-md text-on-surface-variant">
          We&apos;ll email you and send you a notification as soon as your payment is confirmed. This page doesn&apos;t
          show your payment status; your order history shows each order&apos;s current status.
        </p>
        <div className="flex w-full flex-col gap-3 tablet:w-auto tablet:flex-row tablet:flex-wrap tablet:justify-center">
          <Link href="/account/orders" className={buttonLinkClassName("primary")}>
            View your orders
          </Link>
          <Link href="/account/notifications" className={buttonLinkClassName("outline")}>
            View notifications
          </Link>
          <Link href="/shop" className={buttonLinkClassName("ghost")}>
            Continue shopping
          </Link>
        </div>
      </div>
    </Container>
  );
}
