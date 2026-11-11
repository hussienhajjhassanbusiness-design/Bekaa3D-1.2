import type { Metadata } from "next";
import { ContactForm } from "@/components/contact/ContactForm";

export const metadata: Metadata = {
  title: "Contact — Bekaa3D",
};

// FVS (phase 6B-1) — `/contact`, the public contact form
// (POST /api/v1/contact-messages). Guests and signed-in customers alike;
// no account is needed and nothing about an account is revealed.
export default function ContactPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-12 tablet:px-6 desktop:px-8">
      <h1 className="text-h1 font-bold text-text-primary">Contact us</h1>
      <p className="mt-4 text-body text-text-secondary">
        Have a question about an order, a product or anything else? Send us a message and we&apos;ll reply by email.
      </p>
      <ContactForm />
    </div>
  );
}
