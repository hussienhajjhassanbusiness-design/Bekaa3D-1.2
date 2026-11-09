// Cloudflare Turnstile public site key (ADR-025). A site key is public by
// design (it is embedded in every page that renders the widget), so a
// NEXT_PUBLIC_ variable is correct here. The server-side TURNSTILE_SECRET
// lives only in the backend and never in this repository.
//
// Cloudflare's documented always-pass TEST site key. It issues the dummy
// token XXXX.DUMMY.TOKEN.XXXX, which is exactly what the backend's
// CAPTCHA_PROVIDER=fake accepts in development/test (backend .env.example).
// Not a secret.
export const TURNSTILE_TEST_SITE_KEY = "1x00000000000000000000AA";

export interface TurnstileSiteKeyInput {
  siteKey: string | undefined;
  nodeEnv: string | undefined;
}

// Production never falls back to the test key: an unset key there is a
// deployment misconfiguration and the widget shows a safe "unavailable"
// message instead of silently shipping an always-pass key.
export function resolveTurnstileSiteKey({ siteKey, nodeEnv }: TurnstileSiteKeyInput): string | null {
  const trimmed = siteKey?.trim();
  if (trimmed) {
    return trimmed;
  }
  return nodeEnv === "production" ? null : TURNSTILE_TEST_SITE_KEY;
}

export function getTurnstileSiteKey(): string | null {
  return resolveTurnstileSiteKey({
    siteKey: process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY,
    nodeEnv: process.env.NODE_ENV,
  });
}
