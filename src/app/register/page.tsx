"use client";

import { useEffect, useRef, useState } from "react";
import { z } from "zod";
import { useFormContext } from "react-hook-form";
import { Form } from "@/components/forms/Form";
import { TextField } from "@/components/forms/TextField";
import { PasswordField } from "@/components/forms/PasswordField";
import { Button } from "@/components/forms/Button";
import { Alert } from "@/components/feedback/Alert";
import { useRegister } from "@/lib/auth/useRegister";
import { CaptchaWidget } from "@/components/forms/CaptchaWidget";
import { useCaptchaToken } from "@/lib/captcha/useCaptchaToken";
import { captchaFailureMessage, classifyCaptchaFailure } from "@/lib/captcha/captchaErrors";
import type { ReactNode } from "react";

// FVS-002-IMPLEMENTATION-PLAN.md §1 row 3 (confirmed at BATCH 2): 8-256
// Unicode code points, counted via [...password].length (never
// password.length, which counts UTF-16 code units and would over-count
// characters outside the Basic Multilingual Plane). No complexity rule.
// No trimming of email or password anywhere in this schema.
const MIN_PASSWORD_CODE_POINTS = 8;
const MAX_PASSWORD_CODE_POINTS = 256;
const C0_MAX_CODE_POINT = 0x1f;
const DEL_CODE_POINT = 0x7f;

// Deliberately rejects C0 (0x00-0x1F) and DEL (0x7F) control characters
// client-side (§1 row 3). Checked by code point, not a regex literal, to
// operate on the same [...password] code-point array as the length checks
// above rather than a second, separately-encoded representation.
function containsControlCharacter(value: string): boolean {
  return [...value].some((char) => {
    const codePoint = char.codePointAt(0) ?? 0;
    return codePoint <= C0_MAX_CODE_POINT || codePoint === DEL_CODE_POINT;
  });
}

const registerSchema = z.object({
  email: z.string().min(1, "Email is required").email("Enter a valid email address"),
  password: z
    .string()
    .min(1, "Password is required")
    .refine((value) => [...value].length >= MIN_PASSWORD_CODE_POINTS, {
      message: `Password must be at least ${MIN_PASSWORD_CODE_POINTS} characters`,
    })
    .refine((value) => [...value].length <= MAX_PASSWORD_CODE_POINTS, {
      message: `Password must be at most ${MAX_PASSWORD_CODE_POINTS} characters`,
    })
    .refine((value) => !containsControlCharacter(value), {
      message: "Password contains characters that aren't allowed",
    }),
});

type RegisterFormValues = z.infer<typeof registerSchema>;

// §12: only a safe, hardcoded message ever reaches the user — never
// ApiError.raw/detail/type/title/instance. §1 row 13: a 429 gets its own
// safe copy, without fabricating a countdown from the Retry-After header
// (that belongs to the resend flow's confirmed 120s cooldown, T10 — not
// invented here for registration).
const GENERIC_FAILURE_MESSAGE = "Something went wrong. Please try again.";
const RATE_LIMIT_MESSAGE = "Too many attempts. Please wait a bit and try again.";
// §2: identical copy regardless of whether the backend implies a new or
// an existing account — the backend's own `message` field is never read or
// rendered (§1 row 6), since doing so risks silently reintroducing
// enumeration through backend copy this page doesn't control.
const SUCCESS_MESSAGE = "Check your email for a link to verify your account.";

function isRecognizedApiError(value: unknown): value is { kind: string; status?: number } {
  return typeof value === "object" && value !== null && "kind" in value;
}

function failureMessage(error: unknown): string {
  // Captcha refusals (400 CAPTCHA_INVALID, 503, 422 on captcha_token) get
  // their own frontend-owned copy; backend detail/msg is never shown.
  const captchaFailure = classifyCaptchaFailure(error);
  if (captchaFailure) {
    return captchaFailureMessage(captchaFailure);
  }
  if (isRecognizedApiError(error) && error.kind === "http" && error.status === 429) {
    return RATE_LIMIT_MESSAGE;
  }
  return GENERIC_FAILURE_MESSAGE;
}

// A small bridge between Form's React-Hook-Form context and the
// RHF-agnostic TextField/PasswordField primitives (T03/T04) — register()'s
// returned onChange/onBlur/name/ref land on TextField/PasswordField's
// native input passthrough props exactly as they would on a plain <input>;
// ref reaches the real DOM node via React 19's ref-as-prop support (see
// TextField.tsx/PasswordField.tsx), which is what lets Form's
// setFocus-first-invalid-field (§9) actually work here.
function RegisterFields({ captcha }: { captcha: ReactNode }) {
  const {
    register,
    formState: { errors },
  } = useFormContext<RegisterFormValues>();

  return (
    <>
      <TextField
        label="Email"
        // type="text", not "email" — per the HTML living standard, an
        // <input type="email"> automatically strips leading/trailing
        // whitespace from its own .value, which would silently trim the
        // email against the confirmed "not trimmed" contract (§1 row 4)
        // without this component's own code ever choosing to do so.
        type="text"
        inputMode="email"
        autoComplete="email"
        error={errors.email?.message}
        {...register("email")}
      />
      <PasswordField
        label="Password"
        hint="Use 8-256 characters."
        autoComplete="new-password"
        error={errors.password?.message}
        {...register("password")}
      />
      {captcha}
      <Button type="submit" className="mt-4 w-full">
        Create account
      </Button>
    </>
  );
}

export default function Register() {
  const { mutateAsync } = useRegister();
  const {
    siteKey: captchaSiteKey,
    widgetRef: captchaWidgetRef,
    token: captchaToken,
    onToken: onCaptchaToken,
    reset: resetCaptcha,
  } = useCaptchaToken();
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  // FVS-002 BATCH 4 Part C — after the page meaningfully changes to the
  // success state, focus must not silently fall back to <body>. Moves
  // focus to the success heading itself (tabIndex={-1}: a programmatic-
  // only focus target, not part of normal Tab order) rather than building
  // any general focus-management framework.
  const successHeadingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (isSubmitted) {
      successHeadingRef.current?.focus();
    }
  }, [isSubmitted]);

  async function handleSubmit(values: RegisterFormValues) {
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

  if (isSubmitted) {
    return (
      <>
        <h1 ref={successHeadingRef} tabIndex={-1} className="text-h1 font-bold text-text-primary">
          Create your account
        </h1>
        <Alert variant="success" message={SUCCESS_MESSAGE} />
      </>
    );
  }

  return (
    <>
      <h1 className="text-h1 font-bold text-text-primary">Create your account</h1>
      {failure && <Alert variant="error" message={failure} />}
      <Form
        schema={registerSchema}
        defaultValues={{ email: "", password: "" }}
        onSubmit={handleSubmit}
        className="mt-4 max-w-[420px]"
      >
        <RegisterFields
          captcha={<CaptchaWidget ref={captchaWidgetRef} siteKey={captchaSiteKey} onToken={onCaptchaToken} />}
        />
      </Form>
    </>
  );
}
