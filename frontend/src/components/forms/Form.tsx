"use client";

import { useForm, FormProvider, type FieldValues, type DefaultValues, type Resolver } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { ZodType, z } from "zod";
import type { ReactNode } from "react";

export interface FormProps<Schema extends ZodType<FieldValues, FieldValues>> {
  schema: Schema;
  defaultValues?: DefaultValues<z.infer<Schema>>;
  onSubmit: (values: z.infer<Schema>) => void | Promise<void>;
  children: ReactNode;
  className?: string;
}

// FVS002-T05 — the generic integration seam only: semantic <form>, a
// caller-supplied Zod schema (never a hardcoded business schema — that's
// T08/T09/T10's contract-gated job), polite error-summary, focus-first-
// invalid-field on failed submit, and a double-submit guard. No wizard/
// steps/auth-specific logic.
//
// Generic over the Schema itself (not FieldValues directly), deriving the
// value type via z.infer — Zod v4's resolver types don't cleanly propagate
// through a separately-declared FieldValues type parameter.
export function Form<Schema extends ZodType<FieldValues, FieldValues>>({
  schema,
  defaultValues,
  onSubmit,
  children,
  className,
}: FormProps<Schema>) {
  type Values = z.infer<Schema>;
  // zodResolver's own generic inference collapses to the wide `FieldValues`
  // bound when given an abstract `Schema extends ZodType<...>` type
  // parameter rather than a concrete schema, and its exact multi-type-
  // argument signature isn't worth fighting here. One explicit, narrow
  // cast at this single friction point: the resolver zodResolver(schema)
  // produces genuinely does validate against and resolve to `Values`
  // (Values is defined as z.infer<Schema> immediately above) — the runtime
  // behavior is correct, only the generic inference across this library
  // boundary needs the nudge.
  const methods = useForm<Values>({
    resolver: zodResolver(schema) as unknown as Resolver<Values>,
    defaultValues,
  });

  const {
    handleSubmit,
    setFocus,
    formState: { errors, isSubmitting },
  } = methods;

  const errorEntries = Object.entries(errors) as [string, { message?: string } | undefined][];
  // Keyed by field name, not message text — two different invalid fields
  // can legitimately share identical error copy (e.g. two "Required"
  // fields), which would otherwise produce a duplicate React key.
  const errorItems = errorEntries
    .map(([name, error]) => ({ name, message: error?.message }))
    .filter((item): item is { name: string; message: string } => Boolean(item.message));

  function focusFirstInvalidField() {
    const [firstField] = errorEntries;
    if (firstField) {
      setFocus(firstField[0] as never);
    }
  }

  return (
    <FormProvider {...methods}>
      <form onSubmit={handleSubmit(onSubmit, focusFirstInvalidField)} noValidate className={className}>
        {errorItems.length > 0 && (
          <div role="status" aria-live="polite" className="mb-6 rounded-card border border-error/20 bg-error-container p-4 text-on-error-container">
            <p className="text-sm font-semibold">Please fix the following:</p>
            <ul className="mt-1 list-inside list-disc text-sm">
              {errorItems.map(({ name, message }) => (
                <li key={name}>{message}</li>
              ))}
            </ul>
          </div>
        )}
        {/* A native <fieldset disabled> is the double-submit guard: it
            disables every descendant control (including the submit
            Button) the instant isSubmitting flips true, with no extra
            wiring needed per field. display:contents removes it from
            layout entirely — it exists only for its disabling behavior. */}
        <fieldset disabled={isSubmitting} className="contents">
          {children}
        </fieldset>
      </form>
    </FormProvider>
  );
}
