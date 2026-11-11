"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { z } from "zod";
import { useFormContext } from "react-hook-form";
import { Form } from "@/components/forms/Form";
import { TextField } from "@/components/forms/TextField";
import { TextAreaField } from "@/components/forms/TextAreaField";
import { Button } from "@/components/forms/Button";
import { FileUploader } from "@/components/forms/FileUploader";
import { CaptchaWidget } from "@/components/forms/CaptchaWidget";
import { Alert } from "@/components/feedback/Alert";
import { SuccessReceipt } from "@/components/feedback/SuccessReceipt";
import { useCaptchaToken } from "@/lib/captcha/useCaptchaToken";
import { captchaFailureMessage } from "@/lib/captcha/captchaErrors";
import {
  BYI_IMAGE_TYPES,
  BYI_LIMITS,
  useSubmitCustomRequest,
  type CustomRequestFormValues,
} from "@/lib/byi/customRequestApi";
import { describeCustomRequestFailure } from "@/lib/byi/customRequestErrors";
import { isPhoneShaped } from "@/lib/forms/guestFieldRules";

// #FVS-BYI-FORM (phase 6B-2) — exactly the backend's Bring Your Idea fields
// (lib/byi/customRequestApi.ts): contact details, a project title and
// description, three optional free-text preferences, and up to five
// reference images. No STL/3D-file upload, budget, deadline or quantity:
// the backend has none. Client checks mirror the server's rules for fast
// feedback only. The shared FileUploader holds the images in memory
// (deferred mode); they travel in the one multipart request. The single
// CaptchaWidget token is reset after every attempt.

const maxLength = (n: number) => `Use at most ${n} characters.`;

const byiSchema = z.object({
  name: z.string().trim().min(1, "Enter your name.").max(BYI_LIMITS.name, maxLength(BYI_LIMITS.name)),
  email: z
    .string()
    .trim()
    .min(1, "Enter your email address.")
    .max(BYI_LIMITS.email, "Enter a valid email address.")
    .email("Enter a valid email address."),
  phone: z
    .string()
    .trim()
    .min(1, "Enter a phone number.")
    .max(BYI_LIMITS.phone, "Enter a valid phone number.")
    .refine((v) => v === "" || isPhoneShaped(v), "Enter a valid phone number."),
  project_title: z
    .string()
    .trim()
    .min(1, "Give your project a title.")
    .max(BYI_LIMITS.projectTitle, maxLength(BYI_LIMITS.projectTitle)),
  description: z
    .string()
    .trim()
    .min(1, "Describe your idea.")
    .max(BYI_LIMITS.description, maxLength(BYI_LIMITS.description)),
  preferred_material: z.string().trim().max(BYI_LIMITS.preference, maxLength(BYI_LIMITS.preference)),
  preferred_colour: z.string().trim().max(BYI_LIMITS.preference, maxLength(BYI_LIMITS.preference)),
  dimensions: z.string().trim().max(BYI_LIMITS.dimensions, maxLength(BYI_LIMITS.dimensions)),
});

const DEFAULTS: CustomRequestFormValues = {
  name: "",
  email: "",
  phone: "",
  project_title: "",
  description: "",
  preferred_material: "",
  preferred_colour: "",
  dimensions: "",
};

const UPLOAD_CONFIG = {
  allowedMimeTypes: BYI_IMAGE_TYPES,
  maxBytes: BYI_LIMITS.maxAttachmentBytes,
  maxFiles: BYI_LIMITS.maxAttachments,
};

const SUCCESS_MESSAGE = "Thanks — we've received your idea. We'll contact you by email or phone to talk it through.";

function ByiFields({ uploader, captcha }: { uploader: ReactNode; captcha: ReactNode }) {
  const {
    register,
    formState: { errors, isSubmitting },
  } = useFormContext<CustomRequestFormValues>();
  return (
    <div className="flex flex-col gap-4">
      <fieldset className="flex flex-col gap-4">
        <legend className="text-h3 font-semibold text-text-primary">Your details</legend>
        <TextField label="Name" autoComplete="name" maxLength={BYI_LIMITS.name} error={errors.name?.message} {...register("name")} />
        <TextField
          label="Email"
          type="email"
          inputMode="email"
          autoComplete="email"
          maxLength={BYI_LIMITS.email}
          error={errors.email?.message}
          {...register("email")}
        />
        <TextField label="Phone" type="tel" autoComplete="tel" maxLength={BYI_LIMITS.phone} error={errors.phone?.message} {...register("phone")} />
      </fieldset>
      <fieldset className="mt-2 flex flex-col gap-4">
        <legend className="text-h3 font-semibold text-text-primary">Your idea</legend>
        <TextField
          label="Project title"
          maxLength={BYI_LIMITS.projectTitle}
          error={errors.project_title?.message}
          {...register("project_title")}
        />
        <TextAreaField
          label="Description"
          rows={6}
          maxLength={BYI_LIMITS.description}
          hint="What should it do or look like? Up to 5000 characters."
          error={errors.description?.message}
          {...register("description")}
        />
        <TextField
          label="Preferred material (optional)"
          maxLength={BYI_LIMITS.preference}
          error={errors.preferred_material?.message}
          {...register("preferred_material")}
        />
        <TextField
          label="Preferred colour (optional)"
          maxLength={BYI_LIMITS.preference}
          error={errors.preferred_colour?.message}
          {...register("preferred_colour")}
        />
        <TextField
          label="Dimensions (optional)"
          maxLength={BYI_LIMITS.dimensions}
          hint="For example 10 × 5 × 3 cm."
          error={errors.dimensions?.message}
          {...register("dimensions")}
        />
        {uploader}
      </fieldset>
      {captcha}
      <Button type="submit" isLoading={isSubmitting} className="w-full tablet:w-auto">
        Send my idea
      </Button>
    </div>
  );
}

export function BringYourIdeaForm() {
  const { mutateAsync } = useSubmitCustomRequest();
  const {
    siteKey: captchaSiteKey,
    widgetRef: captchaWidgetRef,
    token: captchaToken,
    onToken: onCaptchaToken,
    reset: resetCaptcha,
  } = useCaptchaToken();
  const [attachments, setAttachments] = useState<readonly File[]>([]);
  const [sent, setSent] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [formKey, setFormKey] = useState(0);
  const statusRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (sent) statusRef.current?.focus();
  }, [sent]);

  async function handleSubmit(values: CustomRequestFormValues) {
    setFailure(null);
    if (!captchaToken) {
      setFailure(captchaFailureMessage("missing"));
      return;
    }
    try {
      await mutateAsync({ values, attachments, captchaToken });
      setSent(true);
    } catch (error) {
      setFailure(describeCustomRequestFailure(error, attachments));
    } finally {
      resetCaptcha();
    }
  }

  if (sent) {
    return (
      <div ref={statusRef} tabIndex={-1} className="mt-6 outline-none">
        <SuccessReceipt message={SUCCESS_MESSAGE} />
        <Button
          type="button"
          variant="secondary"
          className="mt-4"
          onClick={() => {
            setSent(false);
            setAttachments([]);
            setFormKey((k) => k + 1);
          }}
        >
          Send another idea
        </Button>
      </div>
    );
  }

  return (
    <div className="mt-6">
      {failure && (
        <div className="mb-4">
          <Alert variant="error" message={failure} />
        </div>
      )}
      <Form key={formKey} schema={byiSchema} defaultValues={DEFAULTS} onSubmit={handleSubmit} className="max-w-[640px]">
        <ByiFields
          uploader={
            <FileUploader
              key={formKey}
              label="Reference images (optional)"
              hint="Up to 5 JPEG, PNG or WebP images, each under 10 MB. Photos or sketches only — no 3D files."
              accept={BYI_IMAGE_TYPES.join(",")}
              config={UPLOAD_CONFIG}
              multiple
              onSelectionChange={setAttachments}
            />
          }
          captcha={<CaptchaWidget ref={captchaWidgetRef} siteKey={captchaSiteKey} onToken={onCaptchaToken} />}
        />
      </Form>
    </div>
  );
}
