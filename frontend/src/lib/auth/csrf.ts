// FVS-003-IMPLEMENTATION-PLAN.md §5 (confirmed BATCH 3A) — csrf_token is the
// ONLY cookie this slice's code may ever read. `access_token`/`refresh_token`
// are httpOnly and must never be read by JS anywhere in this codebase — this
// module does not export any constant or helper that names either of them;
// `readCookie` is generic (and tested against arbitrary names, since it's a
// pure parsing utility), but every real caller in this codebase must go
// through `readCsrfToken()` specifically, never call `readCookie` with a
// different cookie name.

export const CSRF_HEADER_NAME = "X-CSRF-Token";
const CSRF_COOKIE_NAME = "csrf_token";

// Pure and side-effect-free: takes the cookie string directly rather than
// reading `document.cookie` itself, so it's testable without touching the
// real document. Robust against: multiple cookies, no space after ";",
// an unrelated cookie whose name merely contains the target name as a
// substring, percent-encoded values, and malformed percent-encoding (never
// throws — treated as absent rather than guessed).
export function readCookie(cookieString: string, name: string): string | undefined {
  if (!cookieString) {
    return undefined;
  }
  const pairs = cookieString.split(";");
  for (const pair of pairs) {
    const separatorIndex = pair.indexOf("=");
    if (separatorIndex === -1) {
      continue;
    }
    const cookieName = pair.slice(0, separatorIndex).trim();
    if (cookieName !== name) {
      continue;
    }
    const rawValue = pair.slice(separatorIndex + 1).trim();
    try {
      return decodeURIComponent(rawValue);
    } catch {
      return undefined;
    }
  }
  return undefined;
}

export function readCsrfToken(): string | undefined {
  if (typeof document === "undefined") {
    return undefined;
  }
  return readCookie(document.cookie, CSRF_COOKIE_NAME);
}
