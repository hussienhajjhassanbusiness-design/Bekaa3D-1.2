"use client";

import { useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/lib/auth/AuthProvider";
import { AUTH_SESSION_QUERY_KEY } from "@/lib/auth/authSession";
import { Alert } from "@/components/feedback/Alert";
import { Button } from "@/components/forms/Button";
import { PageHeader } from "@/components/ui/PageHeader";
import { Icon } from "@/components/ui/Icon";

const RESEND_VERIFICATION_ROUTE = "/verify-email/resend";
const UNVERIFIED_MESSAGE = "Your email address isn't verified yet.";
const ERROR_MESSAGE = "We couldn't load your profile. Please try again.";

const CARD_CLASSES = "rounded-card border border-outline-variant/30 bg-surface-container-lowest p-6 shadow-sm tablet:p-8";
const TERM_CLASSES = "font-label text-label-sm uppercase tracking-widest text-on-surface-variant";

function ProfileHeader() {
  return (
    <PageHeader eyebrow="Account" title="Profile" description="Your sign-in email and the current state of your account." />
  );
}

// Shapes only, sized like the loaded cards — no fake values.
function ProfileCardSkeleton() {
  const bar = "animate-pulse rounded bg-surface-container-high motion-reduce:animate-none";
  return (
    <div role="status" className="grid grid-cols-1 gap-6 desktop:grid-cols-12">
      <span className="sr-only">Loading profile…</span>
      <div aria-hidden="true" className={`${CARD_CLASSES} flex flex-col items-center gap-4 desktop:col-span-5`}>
        <div className={`h-24 w-24 rounded-full ${bar}`} />
        <div className={`h-5 w-48 ${bar}`} />
        <div className={`h-3 w-32 ${bar}`} />
      </div>
      <div aria-hidden="true" className={`${CARD_CLASSES} flex flex-col gap-4 desktop:col-span-7`}>
        <div className={`h-6 w-40 ${bar}`} />
        <div className={`h-4 w-full ${bar}`} />
        <div className={`h-4 w-2/3 ${bar}`} />
      </div>
    </div>
  );
}

// Display only: the server's ISO instant as "November 2025". An unparsable
// value hides the line rather than showing "Invalid Date".
function formatMemberSince(iso: string): string | null {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric" }).format(date);
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
  const [isRetrying, setIsRetrying] = useState(false);

  async function handleRetry() {
    setIsRetrying(true);
    try {
      await queryClient.refetchQueries({ queryKey: AUTH_SESSION_QUERY_KEY });
    } finally {
      setIsRetrying(false);
    }
  }

  if (isLoading) {
    return (
      <>
        <ProfileHeader />
        <ProfileCardSkeleton />
      </>
    );
  }

  if (isError) {
    return (
      <>
        <ProfileHeader />
        <div className={CARD_CLASSES}>
          <Alert variant="error" message={ERROR_MESSAGE} />
          <Button onClick={handleRetry} isLoading={isRetrying} className="mt-4">
            Retry
          </Button>
        </div>
      </>
    );
  }

  if (!user) {
    // AccountLayout/ProtectedRoute already guarantee this branch is never
    // reached for an anonymous visitor (the redirect fires first) — this
    // only satisfies type narrowing below.
    return null;
  }

  const memberSince = formatMemberSince(user.createdAt);
  // Decorative initial for the Stitch avatar slot (§61); the email itself
  // is the visible identity. No name/photo field exists in /me.
  const initial = user.email.trim().charAt(0).toUpperCase();

  return (
    <>
      <ProfileHeader />
      {!user.emailVerified && (
        <div className="mb-6 flex flex-col items-start gap-3">
          <Alert variant="warning" message={UNVERIFIED_MESSAGE} />
          <Link
            href={RESEND_VERIFICATION_ROUTE}
            className="inline-flex min-h-11 items-center font-semibold text-primary underline underline-offset-4 hover:text-primary-container"
          >
            Resend verification email
          </Link>
        </div>
      )}
      <div className="grid grid-cols-1 gap-6 desktop:grid-cols-12">
        <section
          aria-label="Account identity"
          className={`${CARD_CLASSES} flex flex-col items-center gap-4 text-center desktop:col-span-5`}
        >
          <div
            aria-hidden="true"
            className="flex h-20 w-20 items-center justify-center rounded-full border-4 border-surface-container-high bg-primary font-headline text-headline-lg text-on-primary tablet:h-24 tablet:w-24"
          >
            {initial}
          </div>
          <div className="min-w-0 max-w-full">
            <p className={TERM_CLASSES}>Signed in as</p>
            <p className="mt-2 break-all font-headline text-headline-md text-on-surface">{user.email}</p>
            {memberSince && (
              <p className="mt-3 font-label text-label-caps uppercase text-on-surface-variant">Member since {memberSince}</p>
            )}
          </div>
        </section>

        <section aria-labelledby="profile-details-heading" className={`${CARD_CLASSES} desktop:col-span-7`}>
          <div className="mb-6 flex items-center gap-3">
            <Icon name="person" className="h-6 w-6 text-primary" />
            <h2 id="profile-details-heading" className="font-headline text-headline-md text-on-surface">
              Account details
            </h2>
          </div>
          <dl className="grid grid-cols-1 gap-6 tablet:grid-cols-2">
            <div className="border-b border-outline-variant/40 pb-3">
              <dt className={TERM_CLASSES}>Verification status</dt>
              <dd className="mt-2 flex items-center gap-2 text-body-md text-on-surface">
                <Icon
                  name={user.emailVerified ? "check-circle" : "warning"}
                  className={`h-5 w-5 ${user.emailVerified ? "text-primary" : "text-on-warning-container"}`}
                />
                {user.emailVerified ? "Verified" : "Not verified"}
              </dd>
            </div>
            {/* #ARCHITECTURE-CANONICAL-AUTH-QUERY — DERIVED, not an API field.
                /me has no literal account_state/status field (confirmed —
                FVS-006-IMPLEMENTATION-PLAN.md §1 row 3/4). "Active" is shown
                only because a successful /me response is, per FVS-003's own
                confirmed contract, impossible for an inactive account
                ("account-active state rechecked server-side on every call").
                Never read this from response data — it is always this fixed
                string, shown only when `user` exists at all. */}
            <div className="border-b border-outline-variant/40 pb-3">
              <dt className={TERM_CLASSES}>Account status</dt>
              <dd className="mt-2 text-body-md text-on-surface">Active</dd>
            </div>
          </dl>
        </section>
      </div>
    </>
  );
}
