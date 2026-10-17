// Phase 2 auth/account batch — correction to FVS-004's original design.
// AGENTS.md's confirmed reset-link format is `/reset-password#token=...`:
// the token lives in the URL FRAGMENT, read via `location.hash`, never a
// query parameter — a fragment is never sent to the server in an HTTP
// request, which is exactly why it is the right place for a bearer-style
// credential like this one. Its content is otherwise fully opaque — no
// format, length, or alphabet is assumed or validated anywhere here.

const FAKE_SAME_ORIGIN_BASE = "https://bekaa3d.invalid-origin.local";

// #FVS004-RESET-TOKEN #SECURITY-PASSWORD-RESET-TOKEN
// Takes the hash string directly (e.g. `location.hash`, with or without
// its leading "#") rather than reading `window.location` itself, so it
// stays pure and testable. Fails closed on anything but exactly one
// non-empty `token` entry — a missing, empty, or duplicated parameter is
// never guessed at; all resolve to `null`. The returned value is never
// trimmed, lowercased, or otherwise normalized beyond URLSearchParams' own
// standard percent-decoding — this token is a security-sensitive opaque
// credential the backend alone interprets, and even whitespace-looking
// content must reach it byte-for-byte unchanged.
export function extractResetToken(hash: string): string | null {
  const normalized = hash.startsWith("#") ? hash.slice(1) : hash;
  if (normalized.length === 0) {
    return null;
  }
  const params = new URLSearchParams(normalized);
  const tokens = params.getAll("token");
  if (tokens.length !== 1) {
    return null;
  }
  const token = tokens[0] ?? "";
  return token.length > 0 ? token : null;
}

// #FVS004-RESET-TOKEN #SECURITY-PASSWORD-RESET-TOKEN
// Removes the ENTIRE fragment — the token's only possible location, now
// that it never travels as a query parameter — while preserving the
// pathname and every unrelated query parameter. Callers are expected to
// capture the token via extractResetToken() first, then apply this to
// scrub it from the browser-visible URL (e.g. via history.replaceState)
// immediately after capture. Pure string transform: never touches
// `window`, never navigates, never reloads.
export function removeTokenFromUrl(url: string): string {
  let parsed: URL;
  try {
    parsed = new URL(url, FAKE_SAME_ORIGIN_BASE);
  } catch {
    return url;
  }
  parsed.hash = "";
  const search = parsed.searchParams.toString();
  return parsed.pathname + (search ? `?${search}` : "");
}
