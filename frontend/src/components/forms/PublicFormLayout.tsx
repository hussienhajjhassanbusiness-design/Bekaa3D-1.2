import type { ReactNode } from "react";
import { Container } from "@/components/ui/Container";
import { Icon, type IconName } from "@/components/ui/Icon";

// #PUBLIC-FORM-LAYOUT (redesign Batch 8, PAGE-SPECS S9, COMPONENT-SPECS §9)
//
// Presentation-only frame shared by the two public guest forms (Contact and
// Bring Your Idea): the Stitch boxed hero, then a 7/5 split with the form
// card on the left and an aside on the right (stacked below 1024). It owns no
// state, fields, captcha or submission logic: each form stays its own
// component with its own schema and API call.

export interface PublicFormPageProps {
  title: string;
  description: ReactNode;
  // Factual pill under the description (Stitch's "average response" pill is
  // replaced by real behaviour only — never a response-time promise).
  pill?: { icon: IconName; text: string };
  form: ReactNode;
  aside?: ReactNode;
}

export function PublicFormPage({ title, description, pill, form, aside }: PublicFormPageProps) {
  return (
    <Container className="py-8 tablet:py-12 desktop:py-16">
      <div className="rounded-card border border-outline-variant/20 bg-surface-container-low px-6 py-10 text-center tablet:p-12 desktop:p-20">
        <h1 className="break-words font-display text-display text-on-surface">{title}</h1>
        <div className="mx-auto mt-4 max-w-2xl font-body text-body-lg text-on-surface-variant">{description}</div>
        {pill && (
          <p className="mt-6 inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary-container/10 px-4 py-1.5 font-label text-label-sm uppercase text-on-surface">
            <Icon name={pill.icon} className="h-4 w-4 text-primary" />
            {pill.text}
          </p>
        )}
      </div>
      <div className="mt-10 grid grid-cols-1 gap-gutter tablet:mt-16 desktop:grid-cols-12">
        <div className={`min-w-0 ${aside ? "desktop:col-span-7" : "desktop:col-span-8 desktop:col-start-3"}`}>
          {form}
        </div>
        {aside && <aside className="flex min-w-0 flex-col gap-gutter desktop:col-span-5">{aside}</aside>}
      </div>
    </Container>
  );
}

export interface PublicFormCardProps {
  headingId: string;
  title: string;
  description?: string;
  children: ReactNode;
}

// The white form card (S9 `lg:col-span-7 … rounded-xl p-8 md:p-12`), named by
// its visible h2. Below 640px it is full-bleed (no side border, radius or
// shadow) with a 16px inner gutter, as the Batch 4 auth card, so the 300px
// captcha frame fits at 320px.
export function PublicFormCard({ headingId, title, description, children }: PublicFormCardProps) {
  return (
    <section
      aria-labelledby={headingId}
      className="-mx-margin-mobile border-y border-outline-variant/30 bg-surface-container-lowest px-4 py-8 sm:mx-0 sm:rounded-card sm:border sm:p-8 sm:shadow-sm lg:p-12"
    >
      <h2 id={headingId} className="font-headline text-headline-md text-on-surface tablet:text-headline-lg">
        {title}
      </h2>
      {description && <p className="mt-2 font-body text-body-md text-on-surface-variant">{description}</p>}
      <div className="mt-8">{children}</div>
    </section>
  );
}

export interface PublicAsideCardProps {
  headingId: string;
  title: string;
  children: ReactNode;
  // "tinted": the S9 "Direct Channels" lavender card; "plain": white card.
  tone?: "tinted" | "plain";
}

export function PublicAsideCard({ headingId, title, children, tone = "tinted" }: PublicAsideCardProps) {
  return (
    <section
      aria-labelledby={headingId}
      className={`rounded-card p-6 tablet:p-8 ${
        tone === "tinted"
          ? "bg-surface-container"
          : "border border-outline-variant/30 bg-surface-container-lowest shadow-sm"
      }`}
    >
      <h2 id={headingId} className="font-headline text-headline-md text-on-surface">
        {title}
      </h2>
      <div className="mt-6">{children}</div>
    </section>
  );
}

export interface PublicAsideRowProps {
  icon: ReactNode;
  label: string;
  children: ReactNode;
}

// One S9 channel row: 40px icon tile, mono label, value.
export function PublicAsideRow({ icon, label, children }: PublicAsideRowProps) {
  return (
    <li className="flex items-start gap-4">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-control bg-surface-container-highest text-primary">
        {icon}
      </span>
      <div className="min-w-0">
        <p className="font-label text-label-sm uppercase text-on-surface-variant">{label}</p>
        <div className="mt-1 break-words font-body text-body-md text-on-surface">{children}</div>
      </div>
    </li>
  );
}
