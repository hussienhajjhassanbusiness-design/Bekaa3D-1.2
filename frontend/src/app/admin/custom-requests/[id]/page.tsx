"use client";

import { useParams } from "next/navigation";
import { CustomRequestView } from "@/components/admin/customRequests/CustomRequestView";

// FVS (phase 6B-2) — /admin/custom-requests/[id]
// (GET/PATCH /api/v1/admin/custom-requests/{id}, POST …/transition,
// GET …/attachments/{aid}/download).
export default function AdminCustomRequestPage() {
  const params = useParams<{ id: string }>();
  return <CustomRequestView requestId={params.id} />;
}
