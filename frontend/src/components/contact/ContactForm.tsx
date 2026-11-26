"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { z } from "zod";
import { useFormContext } from "react-hook-form";
import { Form } from "@/components/forms/Form";
import { TextField } from "@/components/forms/TextField";
import { TextAreaField } from "@/components/forms/TextAreaField";
import { Button } from "@/components/forms/Button";
import { Alert } from "@/components/feedback/Alert";
import { Icon } from "@/components/ui/Icon";
import { SuccessReceipt } from "@/components/feedback/SuccessReceipt";
import { CaptchaWidget } from "@/components/forms/CaptchaWidget";
import { useCaptchaToken } from "@/lib/captcha/useCaptchaToken";
import { captchaFailureMessage } from "@/lib/captcha/captchaErrors";
import {
  CONTACT_LIMITS,
  toContactPayload,
  useSubmitContactMessage,
  type ContactFormValues,
} from "@/lib/contact/contactApi";
import { describeGuestSubmissionFailure } from "@/lib/forms/guestSubmissionErrors";
import { isPhoneShaped } from "@/lib/forms/guestFieldRules";

// #FVS-CONTACT-FORM (phase 6B-1) — the public Contact form, exactly the
// backend's ContactMessageCreate fields (see lib/contact/contactApi.ts).
// Client checks mirror the server's rules for fast feedback only; the
// server stays authoritative. The single CaptchaWidget primitive supplies a
// single-use token, reset after every attempt so a retry carries a fresh one.

const FIELD_LABELS: Record<string, string> = {
  name: "Name",
  email: "Email",
  phone: "Phone",
  subject: "Subject",
  message: "Message",
};

const contactSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Enter your name.")
    .max(CONTACT_LIMITS.name, `Use at most ${CONTACT_LIMITS.name} characters.`),
  email: z
    .string()
    .trim()
    .min(1, "Enter your email address.")
    .max(CONTACT_LIMITS.email, "Enter a valid email address.")
    .email("Enter a valid email address."),
  phone: z
    .string()
    .trim()
    .max(CONTACT_LIMITS.phone, "Enter a valid phone number.")
    .refine((v) => v === "" || isPhoneShaped(v), "Enter a valid phone number."),
  subject: z.string().trim().max(CONTACT_LIMITS.subject, `Use at most ${CONTACT_LIMITS.subject} characters.`),
  message: z
    .string()
    .trim()
    .min(1, "Enter a message.")
    .max(CONTACT_LIMITS.message, `Use at most ${CONTACT_LIMITS.message} characters.`),
});

const DEFAULTS: ContactFormValues = { name: "", email: "", phone: "", subject: "", message: "" };

const SUCCESS_MESSAGE = "Thanks — your message has been sent. We'll reply by email.";

function ContactFields({ captcha }: { captcha: ReactNode }) {
  const {
    register,
    formState: { errors, isSubmitting },
  } = useFormContext<ContactFormValues>();
  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-6 tablet:grid-cols-2">
        <div className="min-w-0">
          <TextField
            label="Name"
            autoComplete="name"
            maxLength={CONTACT_LIMITS.name}
            error={errors.name?.message}
            {...register("name")}
          />
        </div>
        <div className="min-w-0">
          <TextField
            label="Email"
            type="email"
            inputMode="email"
            autoComplete="email"
            maxLength={CONTACT_LIMITS.email}
            error={errors.email?.message}
            {...register("email")}
          />
        </div>
        <div className="min-w-0">
          <TextField
            label="Phone (optional)"
            type="tel"
            autoComplete="tel"
            maxLength={CONTACT_LIMITS.phone}
            error={errors.phone?.message}
            {...register("phone")}
          />
        </div>
        <div className="min-w-0">
          <TextField
            label="Subject (optional)"
            maxLength={CONTACT_LIMITS.subject}
            error={errors.subject?.message}
            {...register("subject")}
          />
        </div>
      </div>
      <TextAreaField
        label="Message"
        rows={6}
        maxLength={CONTACT_LIMITS.message}
        hint={`Up to ${CONTACT_LIMITS.message} characters.`}
        error={errors.message?.message}
        {...register("message")}
      />
      {captcha}
      <div>
        <Button type="submit" size="lg" isLoading={isSubmitting} className="w-full tablet:w-auto">
          Send message
          {!isSubmitting && <Icon name="send" className="h-5 w-5" />}
        </Button>
      </div>
    </div>
  );
}

export function ContactForm() {
  const { mutateAsync } = useSubmitContactMessage();
  const {
    siteKey: captchaSiteKey,
    widgetRef: captchaWidgetRef,
    token: captchaToken,
    onToken: onCaptchaToken,
    reset: resetCaptcha,
  } = useCaptchaToken();
  const [sent, setSent] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  // Remounts the form (fresh values) for "Send another message".
  const [formKey, setFormKey] = useState(0);
  const statusRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (sent) statusRef.current?.focus();
  }, [sent]);

  async function handleSubmit(values: ContactFormValues) {
    setFailure(null);
    if (!captchaToken) {
      setFailure(captchaFailureMessage("missing"));
      return;
    }
    try {
      await mutateAsync(toContactPayload(values, captchaToken));
      setSent(true);
    } catch (error) {
      setFailure(describeGuestSubmissionFailure(error, FIELD_LABELS).message);
    } finally {
      // Single-use token: the next attempt must carry a fresh one.
      resetCaptcha();
    }
  }

  if (sent) {
    return (
      <div ref={statusRef} tabIndex={-1} className="outline-none">
        <SuccessReceipt
          title="Message sent"
          message={SUCCESS_MESSAGE}
          actions={
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setSent(false);
                setFormKey((k) => k + 1);
              }}
            >
              Send another message
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div>
      {failure && (
        <div className="mb-6">
          <Alert variant="error" message={failure} />
        </div>
      )}
      <Form key={formKey} schema={contactSchema} defaultValues={DEFAULTS} onSubmit={handleSubmit}>
        <ContactFields
          captcha={<CaptchaWidget ref={captchaWidgetRef} siteKey={captchaSiteKey} onToken={onCaptchaToken} />}
        />
      </Form>
    </div>
  );
}
