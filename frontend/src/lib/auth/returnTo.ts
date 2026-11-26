// FVS-003-IMPLEMENTATION-PLAN.md §12 — a safe, same-origin-relative-path-only
// validator. Pure (no `window`, no DOM, no router dependency) and
// contract-independent: this is this slice's own architecture decision
// (§2 row 39), not something the backend confirms or denies.
//
// A valid value must begin with exactly one "/" and must never resolve, once
// decoded, to anything other than a path on the app's own origin. Backslashes
// are rejected outright rather than normalized, since some browsers treat a
// backslash as a path separator when resolving a URL, which could otherwise
// turn a value like "/\evil.example" into a protocol-relative redirect.

const FAKE_SAME_ORIGIN_BASE = "https://bekaa3d.invalid-origin.local";

function containsUnsafeDecodedPattern(value: string): boolean {
  let decoded: string;
  try {
    decoded = decodeURIComponent(value);
  } catch {
    // Malformed percent-encoding (e.g. a lone "%", or "%zz") must never
    // throw out of this function — treated as unsafe, not as an error.
    return true;
  }
  return decoded.startsWith("//") || decoded.includes("\\");
}

export function isSafeReturnTo(value: unknown): value is string {
  if (typeof value !== "string" || value.length === 0) {
    return false;
  }
  if (!value.startsWith("/") || value.startsWith("//")) {
    return false;
  }
  if (value.includes("\\")) {
    return false;
  }
  if (containsUnsafeDecodedPattern(value)) {
    return false;
  }

  try {
    const resolved = new URL(value, FAKE_SAME_ORIGIN_BASE);
    return resolved.origin === FAKE_SAME_ORIGIN_BASE;
  } catch {
    return false;
  }
}

const DEFAULT_RETURN_TO = "/";

export function resolveReturnTo(value: string | null | undefined): string {
  return isSafeReturnTo(value) ? value : DEFAULT_RETURN_TO;
}

// Produces "/login?returnTo=<encoded-safe-relative-path>" — purely local and
// deterministic, no navigation performed here. The raw, unsafe candidate
// (if any) is never embedded in the result; only the resolved, already-safe
// path is encoded.
export function buildLoginRedirectPath(value: string | null | undefined): string {
  const safePath = resolveReturnTo(value);
  return `/login?returnTo=${encodeURIComponent(safePath)}`;
}
