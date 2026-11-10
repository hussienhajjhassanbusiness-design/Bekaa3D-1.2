import type { Metadata } from "next";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { CheckoutView } from "@/components/checkout/CheckoutView";

// Phase 5D (FVS-026) — checkout against the real POST /api/v1/checkout.
// A verified customer session is required, so the route sits behind the
// real ProtectedRoute (anonymous -> /login?returnTo=%2Fcheckout); the
// view itself handles an unverified account with guidance. AppLayout
// supplies the one <main> landmark.
export const metadata: Metadata = {
  title: "Checkout — Bekaa3D",
};

export default function CheckoutRoutePage() {
  return (
    <ProtectedRoute>
      <CheckoutView />
    </ProtectedRoute>
  );
}
