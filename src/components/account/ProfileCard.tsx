"use client";

import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/lib/auth/AuthProvider";
import { AUTH_SESSION_QUERY_KEY } from "@/lib/auth/authSession";
import { Alert } from "@/components/feedback/Alert";
import { Button } from "@/components/forms/Button";

const RESEND_VERIFICATION_ROUTE = "/verify-email/resend";
const UNVERIFIED_MESSAGE = "Your email address isn't verified yet.";
const ERROR_MESSAGE = "We couldn't load your profile. Please try again.";

function ProfileCardSkeleton() {
  return (
    <div role="status">
      <span className="sr-only">Loading profile…</span>
      <div aria-hidden="true" className="h-6 w-48 animate-pulse rounded bg-neutral-200 motion-reduce:animate-none" />
      <div
        aria-hidden="true"
        className="mt-4 h-4 w-64 animate-pulse rounded bg-neutral-200 motion-reduce:animate-none"
      />
      <div
        aria-hidden="true"
        className="mt-2 h-4 w-40 animate-pulse rounded bg-neutral-200 motion-reduce:animate-none"
      />
    </div>
  );
}

// #FVS006-ACCOUNT-SHELL
//
// Read-only — VS-006 defines no mutable profile field for V1, so this
// component never renders an input/textarea/select or a Save/Edit/Cancel
// control. Reads useAuth() directly; retry re-triggers the SAME canonical
// ["auth","session"] query (never a second fetch path) via
// queryClient.refetchQueries, exactly as useLogout/useLogin already do
// for the same query key.
export function ProfileCard() {
  const { user, isLoading, isError } = useAuth();
  const queryClient = useQueryClient();

  function handleRetry() {
    void queryClient.refetchQueries({ queryKey: AUTH_SESSION_QUERY_KEY });
  }

  if (isLoading) {
    return <ProfileCardSkeleton />;
  }

  if (isError) {
    return (
      <div>
        <Alert variant="error" message={ERROR_MESSAGE} />
        <Button onClick={handleRetry} className="mt-4">
          Retry
        </Button>
      </div>
    );
  }

  if (!user) {
    // AccountLayout/ProtectedRoute already guarantee this branch is never
    // reached for an anonymous visitor (the redirect fires first) — this
    // only satisfies type narrowing below.
    return null;
  }

  return (
    <div>
      <h1 className="text-h1 font-bold text-text-primary">Profile</h1>
      {!user.emailVerified && (
        <div className="mt-4">
          <Alert variant="warning" message={UNVERIFIED_MESSAGE} />
          <Link href={RESEND_VERIFICATION_ROUTE} className="mt-2 inline-block text-text-link underline">
            Resend verification email
          </Link>
        </div>
      )}
      <dl className="mt-4">
        <dt className="text-label font-semibold uppercase tracking-label text-text-secondary">Email</dt>
        <dd className="text-body text-text-primary">{user.email}</dd>
        <dt className="mt-3 text-label font-semibold uppercase tracking-label text-text-secondary">
          Verification status
        </dt>
        <dd className="text-body text-text-primary">{user.emailVerified ? "Verified" : "Not verified"}</dd>
        {/* #ARCHITECTURE-CANONICAL-AUTH-QUERY — DERIVED, not an API field.
            /me has no literal account_state/status field (confirmed —
            FVS-006-IMPLEMENTATION-PLAN.md §1 row 3/4). "Active" is shown
            only because a successful /me response is, per FVS-003's own
            confirmed contract, impossible for an inactive account
            ("account-active state rechecked server-side on every call").
            Never read this from response data — it is always this fixed
            string, shown only when `user` exists at all. */}
        <dt className="mt-3 text-label font-semibold uppercase tracking-label text-text-secondary">
          Account status
        </dt>
        <dd className="text-body text-text-primary">Active</dd>
      </dl>
    </div>
  );
}
