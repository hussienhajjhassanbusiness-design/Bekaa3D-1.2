import type { Metadata } from "next";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { CartView } from "@/components/cart/CartView";

// Phase 5C (FVS-025) — the customer's cart, wired to the real
// /api/v1/cart contract. GET /cart needs a session, so the route sits
// behind the real ProtectedRoute (anonymous -> /login?returnTo=%2Fcart);
// there is no guest cart. AppLayout supplies the one <main> landmark.
export const metadata: Metadata = {
  title: "Cart — Bekaa3D",
};

export default function CartRoutePage() {
  return (
    <ProtectedRoute>
      <CartView />
    </ProtectedRoute>
  );
}
