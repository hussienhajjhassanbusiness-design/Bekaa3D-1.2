import type { Metadata } from "next";
import { BringYourIdeaForm } from "@/components/byi/BringYourIdeaForm";

export const metadata: Metadata = {
  title: "Bring Your Idea — Bekaa3D",
};

// FVS (phase 6B-2) — `/bring-your-idea` (POST /api/v1/custom-requests). A
// request for a custom print: a lead the team follows up off the platform,
// never an order or a payment. No account needed.
export default function BringYourIdeaPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-12 tablet:px-6 desktop:px-8">
      <h1 className="text-h1 font-bold text-text-primary">Bring your idea</h1>
      <p className="mt-4 text-body text-text-secondary">
        Have something in mind that isn&apos;t in the shop? Tell us about it and add a few reference photos or sketches. We&apos;ll
        get back to you to discuss the details and a quote. Sending a request doesn&apos;t place an order or charge you anything.
      </p>
      <BringYourIdeaForm />
    </div>
  );
}
