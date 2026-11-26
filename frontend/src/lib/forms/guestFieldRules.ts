// Client-side mirrors of the backend's shared guest-form rules (backend
// 2dfb27b engagement/domain/contact_message.py: PHONE_PATTERN,
// PHONE_MIN_DIGITS; the email rule `3 <= len <= 254 and "@" not first`).
// UX only — the server stays authoritative and re-checks everything.
const PHONE_PATTERN = /^\+?[0-9 ().-]{6,31}$/;
const PHONE_MIN_DIGITS = 6;

export function isPhoneShaped(value: string): boolean {
  const digits = value.replace(/[^0-9]/g, "").length;
  return PHONE_PATTERN.test(value) && digits >= PHONE_MIN_DIGITS;
}
