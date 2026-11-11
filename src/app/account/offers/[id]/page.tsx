"use client";

import { useParams } from "next/navigation";
import { CustomerOfferView } from "@/components/offers/CustomerOfferView";

// FVS (phase 6C) — one of the customer's own offers,
// GET /api/v1/me/offers/{offer_id}. Protection comes from AccountLayout.
export default function AccountOfferDetailPage() {
  const params = useParams<{ id: string }>();
  return <CustomerOfferView offerId={typeof params.id === "string" ? params.id : ""} />;
}
