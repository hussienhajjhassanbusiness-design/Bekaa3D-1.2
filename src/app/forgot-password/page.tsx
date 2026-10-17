"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { z } from "zod";
import { useFormContext } from "react-hook-form";
import { Form } from "@/components/forms/Form";
import { TextField } from "@/components/forms/TextField";
import { Button } from "@/components/forms/Button";
import { Alert } from "@/components/feedback/Alert";
import { usePasswordResetRequest } from "@/lib/auth/usePasswordResetRequest";
import type { ApiError } from "@/lib/api/ApiError";

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

function ForgotPasswordFields() {
  const {
    register,
    formState: { errors },
  } = useFormContext<ForgotPasswordFormValues>();

  return (
    <>
      <TextField
        label="Email"
        type="text"
        inputMode="email"
        autoComplete="email"
        error={errors.email?.message}
        {...register("email")}
      />
      <Button type="submit" className="mt-4 w-full">
        Send reset link
      </Button>
    </>
  );
}

export default function ForgotPassword() {
  const { mutateAsync } = usePasswordResetRequest();
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
    try {
      await mutateAsync(values);
      setIsSubmitted(true);
    } catch (error) {
      setFailure(failureMessage(error));
    }
  }

  return (
    <>
      <h1 ref={headingRef} tabIndex={-1} className="text-h1 font-bold text-text-primary">
        Reset your password
      </h1>
      {isSubmitted ? (
        <Alert variant="success" message={SUCCESS_MESSAGE} />
      ) : (
        <>
          {failure && <Alert variant="error" message={failure} />}
          <Form
            schema={forgotPasswordSchema}
            defaultValues={{ email: "" }}
            onSubmit={handleSubmit}
            className="mt-4 max-w-[420px]"
          >
            <ForgotPasswordFields />
          </Form>
        </>
      )}
      <p className="mt-4 text-body text-text-secondary">
        Remembered your password?{" "}
        <Link href="/login" className="text-text-link underline">
          Log in
        </Link>
      </p>
    </>
  );
}
