import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/apiClient";

// #FVS-CONTACT (phase 6B-1) — POST /api/v1/contact-messages (backend 2dfb27b,
// engagement/api/contact_messages.py, contact_message_schemas.py; VS-033,
// FR-16). Public: no auth cookie or CSRF header required; guests submit.
// Body (extra="forbid"):
//   name          required, 1-100 after trim
//   email         required, an email address (<= 254)
//   phone         optional, <= 32, phone-shaped (+, digits, space ( ) . -, >= 6 digits)
//   subject       optional, <= 200
//   message       required, 1-5000 after trim, line breaks allowed
//   captcha_token required, Cloudflare Turnstile token
// 201 -> {id, created_at}. The receipt id is never shown to the visitor.
// Hourly limits: 60 attempts, then 5 per IP and 5 per email address.
export const CONTACT_LIMITS = {
  name: 100,
  email: 254,
  phone: 32,
  subject: 200,
  message: 5000,
} as const;

export interface ContactMessageCreateDTO {
  name: string;
  email: string;
  phone?: string;
  subject?: string;
  message: string;
  captcha_token: string;
}

export interface ContactMessageReceiptDTO {
  id: string;
  created_at: string;
}

export interface ContactFormValues {
  name: string;
  email: string;
  phone: string;
  subject: string;
  message: string;
}

// Exact wire payload: trimmed, blank optionals omitted (the server treats a
// blank optional as absent either way).
export function toContactPayload(values: ContactFormValues, captchaToken: string): ContactMessageCreateDTO {
  const phone = values.phone.trim();
  const subject = values.subject.trim();
  return {
    name: values.name.trim(),
    email: values.email.trim(),
    ...(phone ? { phone } : {}),
    ...(subject ? { subject } : {}),
    message: values.message.trim(),
    captcha_token: captchaToken,
  };
}

export function submitContactMessage(body: ContactMessageCreateDTO): Promise<ContactMessageReceiptDTO> {
  return apiClient.post<ContactMessageReceiptDTO>("/api/v1/contact-messages", body);
}

// A write never auto-retries: each attempt spends a single-use captcha token.
export function useSubmitContactMessage() {
  return useMutation({ mutationFn: submitContactMessage, retry: false });
}
