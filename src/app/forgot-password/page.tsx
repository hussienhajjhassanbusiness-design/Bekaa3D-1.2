"use client";

import { useEffect, useRef, useState } from "react";
import { z } from "zod";
import { useFormContext } from "react-hook-form";
import { Form } from "@/components/forms/Form";
import { TextField } from "@/components/forms/TextField";
import { Button } from "@/components/forms/Button";
import { Alert } from "@/components/feedback/Alert";
import { usePasswordResetRequest } from "@/lib/auth/usePasswordResetRequest";
import type { ApiError } from "@/lib/api/ApiError";
import type { ReactNode } from "react";
import { CaptchaWidget } from "@/components/forms/CaptchaWidget";
import { useCaptchaToken } from "@/lib/captcha/useCaptchaToken";
import { captchaFailureMessage, classifyCaptchaFailure } from "@/lib/captcha/captchaErrors";
import { AuthBackToLogin, AuthShell } from "@/components/auth/AuthShell";
import { Icon } from "@/components/ui/Icon";

// Phase 2 auth/account batch (FVS-004, request half) — same generic,
// non-authoritative email-shape rule already established by registration/
// resend; no new rule invented here.
const forgotPasswordSchema = z.object({
  email: z.string().min(1, "Email is required").email("Enter a valid email address"),
});

type ForgotPasswordFormValues = z.infer<typeof forgotPasswordSchema>;

// "Request response must not reveal whether an account exists" — identical
// copy regardless of the mocked/real outcome, same enumeration-safety rule
// register/resend already follow. The backend's own `message` field is
// never read or rendered.
const SUCCESS_MESSAGE = "If an account exists for that email, a password reset link has been sent.";
const GENERIC_FAILURE_MESSAGE = "Something went wrong. Please try again.";
const NETWORK_MESSAGE = "We couldn't reach the server. Please try again.";
const TIMEOUT_MESSAGE = "The server took too long to respond. Please try again.";
const RATE_LIMIT_MESSAGE_GENERIC = "Too many attempts. Please try again later.";
const RATE_LIMIT_MESSAGE_WITH_WAIT = (seconds: number) => `Too many attempts. Please wait about ${seconds} seconds and try again.`;

function isRecognizedApiError(value: unknown): value is ApiError {
  return typeof value === "object" && value !== null && "kind" in value;
}

function failureMessage(error: unknown): string {
  // Captcha refusals (400 CAPTCHA_INVALID, 503, 422 on captcha_token) get
  // frontend-owned copy; backend detail/msg is never shown.
  const captchaFailure = classifyCaptchaFailure(error);
  if (captchaFailure) {
    return captchaFailureMessage(captchaFailure);
  }
  if (isRecognizedApiError(error)) {
    if (error.kind === "network") {
      return NETWORK_MESSAGE;
    }
    if (error.kind === "timeout") {
      return TIMEOUT_MESSAGE;
    }
    if (error.kind === "http" && error.status === 429) {
      return error.retryAfterSeconds !== undefined
        ? RATE_LIMIT_MESSAGE_WITH_WAIT(error.retryAfterSeconds)
        : RATE_LIMIT_MESSAGE_GENERIC;
    }
  }
  return GENERIC_FAILURE_MESSAGE;
}

function ForgotPasswordFields({ captcha }: { captcha: ReactNode }) {
  const {
    register,
    formState: { errors, isSubmitting },
  } = useFormContext<ForgotPasswordFormValues>();

  return (
    <>
      <TextField
        label="Email"
        type="text"
        inputMode="email"
        autoComplete="email"
        leadingIcon="mail"
        error={errors.email?.message}
        {...register("email")}
      />
      {captcha}
      <Button type="submit" size="lg" isLoading={isSubmitting} className="w-full">
        Send reset link
        <Icon name="arrow-forward" className="h-4 w-4" />
      </Button>
    </>
  );
}

export default function ForgotPassword() {
  const { mutateAsync } = usePasswordResetRequest();
  const {
    siteKey: captchaSiteKey,
    widgetRef: captchaWidgetRef,
    token: captchaToken,
    onToken: onCaptchaToken,
    reset: resetCaptcha,
  } = useCaptchaToken();
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (isSubmitted) {
      headingRef.current?.focus();
    }
  }, [isSubmitted]);

  async function handleSubmit(values: ForgotPasswordFormValues) {
    setFailure(null);
    if (!captchaToken) {
      setFailure(captchaFailureMessage("missing"));
      return;
    }
    try {
      await mutateAsync({ ...values, captcha_token: captchaToken });
      setIsSubmitted(true);
    } catch (error) {
      setFailure(failureMessage(error));
      // Turnstile tokens are single-use: the next attempt needs a new one.
      resetCaptcha();
    }
  }

  // Batch 4: Stitch A3 card (left-aligned heading, leading-icon email
  // field, "Back to log in"). The description stays enumeration-safe: it
  // never implies that the address belongs to an account.
  return (
    <AuthShell
      align="start"
      title="Reset your password"
      titleRef={headingRef}
      status={isSubmitted ? { icon: "mail", tone: "success" } : undefined}
      description={
        isSubmitted
          ? undefined
          : "Enter the email address you use for Bekaa3D. If it matches an account, we\u2019ll send a link to choose a new password."
      }
    >
      {isSubmitted ? (
        <Alert variant="success" message={SUCCESS_MESSAGE} />
      ) : (
        <>
          {failure && <Alert variant="error" message={failure} />}
          <Form
            schema={forgotPasswordSchema}
            defaultValues={{ email: "" }}
            onSubmit={handleSubmit}
            className="flex flex-col gap-5"
          >
            <ForgotPasswordFields
              captcha={
                <CaptchaWidget ref={captchaWidgetRef} siteKey={captchaSiteKey} onToken={onCaptchaToken} align="center" />
              }
            />
          </Form>
        </>
      )}
      <AuthBackToLogin />
    </AuthShell>
  );
}
