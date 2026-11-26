"use client";

import { useParams } from "next/navigation";
import { ContactMessageView } from "@/components/admin/contact/ContactMessageView";

// FVS (phase 6B-1) — /admin/contact-messages/[id]
// (GET/PATCH /api/v1/admin/contact-messages/{id}).
export default function AdminContactMessagePage() {
  const params = useParams<{ id: string }>();
  return <ContactMessageView messageId={params.id} />;
}
