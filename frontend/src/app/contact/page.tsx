import type { Metadata } from "next";
import { ContactForm } from "@/components/contact/ContactForm";
import { ContactChannels } from "@/components/contact/ContactChannels";
import { PublicFormCard, PublicFormPage } from "@/components/forms/PublicFormLayout";

export const metadata: Metadata = {
  title: "Contact — Bekaa3D",
};

// FVS (phase 6B-1) — `/contact`, the public contact form
// (POST /api/v1/contact-messages). Guests and signed-in customers alike;
// no account is needed and nothing about an account is revealed.
// Redesign Batch 8: Stitch S9 boxed hero + 7/5 form card / channels aside.
export default function ContactPage() {
  return (
    <PublicFormPage
      title="Contact us"
      description={
        <p>
          Have a question about an order, a product or anything else? Send us a message and we&apos;ll reply by email.
        </p>
      }
      pill={{ icon: "mail", text: "We reply by email" }}
      form={
        <PublicFormCard
          headingId="contact-form-heading"
          title="Write to us"
          description="Fields marked optional can be left empty."
        >
          <ContactForm />
        </PublicFormCard>
      }
      aside={<ContactChannels />}
    />
  );
}
