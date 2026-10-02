import { ProfileCard } from "@/components/account/ProfileCard";

// FVS-006-IMPLEMENTATION-PLAN.md T04 — AccountLayout (mounted via
// src/app/account/layout.tsx) already supplies the ProtectedRoute
// boundary, nav, and content landmark. This page renders only the real
// content.
export default function AccountProfilePage() {
  return <ProfileCard />;
}
