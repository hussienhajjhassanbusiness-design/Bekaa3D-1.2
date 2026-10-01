// FVS-004-IMPLEMENTATION-PLAN.md T01 (CAN IMPLEMENT NOW — contract-
// independent). The reset link's `token` query parameter name is the only
// thing FVS-004 confirms about this link (FRONTEND-VERTICAL-SLICE-PLAN.md's
// own routing table: `/reset-password` + token query param). Its content
// is otherwise fully opaque — no format, length, or alphabet is assumed or
// validated anywhere here, since the backend has never specified one.

const FAKE_SAME_ORIGIN_BASE = "https://bekaa3d.invalid-origin.local";

// #FVS004-RESET-TOKEN #SECURITY-PASSWORD-RESET-TOKEN
// Fails closed on anything but exactly one non-empty value — a missing,
// empty, or duplicated `token` parameter is never guessed at (e.g. "pick
// the first one"); all resolve to `null`. The returned value is never
// trimmed, lowercased, or otherwise normalized beyond URLSearchParams' own
// standard percent-decoding — this token is a security-sensitive opaque
// credential the backend alone interprets, and even whitespace-looking
// content must reach it byte-for-byte unchanged. Future changes must not
// add any "cleanup" of this value.
export function extractResetToken(params: URLSearchParams): string | null {
  const tokens = params.getAll("token");
  if (tokens.length !== 1) {
    return null;
  }
  const token = tokens[0] ?? "";
  return token.length > 0 ? token : null;
}

// #FVS004-RESET-TOKEN #SECURITY-PASSWORD-RESET-TOKEN
// Pure string transform — removes only the `token` query parameter from a
// path+query(+hash) string, preserving everything else. Callers are
// expected to capture the token via extractResetToken() first, then apply
// this to scrub it from the browser-visible URL (e.g. via
// history.replaceState) — this function itself never touches `window`,
// never navigates, and never reloads, so it stays unit-testable and so a
// caller cannot accidentally trigger a second request by using it.
export function removeTokenFromUrl(url: string): string {
  let parsed: URL;
  try {
    parsed = new URL(url, FAKE_SAME_ORIGIN_BASE);
  } catch {
    return url;
  }
  parsed.searchParams.delete("token");
  const search = parsed.searchParams.toString();
  return parsed.pathname + (search ? `?${search}` : "") + parsed.hash;
}
