export type DownloadNoticeKind = "cap" | "revoked" | "generic";

export interface DownloadNoticeProps {
  kind: DownloadNoticeKind;
  // Already-safe string from a future adapter, shown verbatim. Never
  // calculated client-side — Retry-After/reset-time semantics are
  // unconfirmed (FVS-021-IMPLEMENTATION-PLAN.md §1).
  resetTimeLabel?: string;
}

const BASE_COPY: Record<DownloadNoticeKind, string> = {
  cap: "You've reached today's download limit.",
  revoked: "This download is no longer available.",
  generic: "Something went wrong. Please try again.",
};

// #FVS021-DOWNLOAD-NOTICE
//
// Safe presentational notices only — no backend status/RFC code is
// mapped here (a future adapter's job), and this component is never
// wired to a pre-flight fetch. The native anchor download architecture
// (#ARCHITECTURE-NATIVE-STL-DOWNLOAD) stays authoritative; these
// notices render from state a parent already has, never from a
// check-before-click request this component triggers itself.
export function DownloadNotice({ kind, resetTimeLabel }: DownloadNoticeProps) {
  const message = kind === "cap" && resetTimeLabel ? `${BASE_COPY.cap} Try again ${resetTimeLabel}.` : BASE_COPY[kind];

  return (
    <p role="alert" className="text-caption text-danger">
      {message}
    </p>
  );
}
