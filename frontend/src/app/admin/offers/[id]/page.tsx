"use client";

import { useParams } from "next/navigation";
import { AdminOfferView } from "@/components/admin/offers/AdminOfferView";

// FVS (phase 6C) — /admin/offers/[id] (GET /api/v1/admin/offers/{id}, and
// accept / counter / reject).
export default function AdminOfferPage() {
  const params = useParams<{ id: string }>();
  return <AdminOfferView offerId={typeof params.id === "string" ? params.id : ""} />;
}
