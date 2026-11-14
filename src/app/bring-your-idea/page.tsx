import type { Metadata } from "next";
import { BringYourIdeaForm } from "@/components/byi/BringYourIdeaForm";
import { PublicAsideCard, PublicAsideRow, PublicFormCard, PublicFormPage } from "@/components/forms/PublicFormLayout";
import { Icon } from "@/components/ui/Icon";

export const metadata: Metadata = {
  title: "Bring Your Idea — Bekaa3D",
};

// FVS (phase 6B-2) — `/bring-your-idea` (POST /api/v1/custom-requests). A
// request for a custom print: a lead the team follows up off the platform,
// never an order or a payment. No account needed.
// Redesign Batch 8 (DERIVED: S9 hero + form card, D8 dropzone). The aside only
// restates real behaviour and the real upload limits — no turnaround promise,
// price, quote amount or tracking.
export default function BringYourIdeaPage() {
  return (
    <PublicFormPage
      title="Bring your idea"
      description={
        <p>
          Have something in mind that isn&apos;t in the shop? Tell us about it and add a few reference photos or
          sketches. We&apos;ll get back to you to discuss the details and a quote. Sending a request doesn&apos;t place
          an order or charge you anything.
        </p>
      }
      pill={{ icon: "lightbulb", text: "No order, no payment" }}
      form={
        <PublicFormCard
          headingId="byi-form-heading"
          title="Describe your project"
          description="Fields marked optional can be left empty."
        >
          <BringYourIdeaForm />
        </PublicFormCard>
      }
      aside={
        <>
          <PublicAsideCard headingId="byi-next-heading" title="What happens next">
            <ol className="flex flex-col gap-6">
              <PublicAsideRow icon={<Icon name="send" className="h-5 w-5" />} label="1 · You send it">
                Your details, a description and up to five reference images.
              </PublicAsideRow>
              <PublicAsideRow icon={<Icon name="call" className="h-5 w-5" />} label="2 · We contact you">
                We get in touch by email or phone to talk through the details and a quote.
              </PublicAsideRow>
              <PublicAsideRow icon={<Icon name="verified" className="h-5 w-5" />} label="3 · You decide">
                Sending a request doesn&apos;t place an order or charge you anything.
              </PublicAsideRow>
            </ol>
          </PublicAsideCard>
          <PublicAsideCard headingId="byi-images-heading" title="Reference images" tone="plain">
            <ul className="flex flex-col gap-3 font-body text-body-md text-on-surface-variant">
              <li className="flex items-start gap-3">
                <Icon name="image" className="mt-0.5 h-5 w-5 text-primary" />
                Up to 5 JPEG, PNG or WebP images.
              </li>
              <li className="flex items-start gap-3">
                <Icon name="upload-file" className="mt-0.5 h-5 w-5 text-primary" />
                Each image under 10 MB.
              </li>
              <li className="flex items-start gap-3">
                <Icon name="info" className="mt-0.5 h-5 w-5 text-primary" />
                Photos or sketches only — no 3D files.
              </li>
            </ul>
          </PublicAsideCard>
        </>
      }
    />
  );
}
