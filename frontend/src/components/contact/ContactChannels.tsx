"use client";

import Link from "next/link";
import { PublicAsideCard, PublicAsideRow } from "@/components/forms/PublicFormLayout";
import { buttonLinkClassName } from "@/components/forms/Button";
import { Icon } from "@/components/ui/Icon";
import { WhatsAppGlyph } from "@/components/ui/WhatsAppGlyph";
import { buildWhatsAppHref } from "@/lib/catalog/whatsapp";
import { usePublicSettings } from "@/lib/settings/usePublicSettings";

// #CONTACT-CHANNELS (redesign Batch 8, PAGE-SPECS S9 "Direct Channels")
//
// Only real Bekaa3D information: the reply channel the form itself uses
// (email), and the WhatsApp number / pickup address / pickup hours from the
// shared public-settings query — each row renders only when configured.
// No invented email address, phone, office, opening hours, map or social
// links (Stitch's are mock data).
export function ContactChannels() {
  const settings = usePublicSettings().data;
  const whatsappHref = settings?.whatsappNumber ? buildWhatsAppHref(settings.whatsappNumber) : null;

  return (
    <>
      <PublicAsideCard headingId="contact-channels-heading" title="Other ways to reach us">
        <ul className="flex flex-col gap-6">
          <PublicAsideRow icon={<Icon name="mail" className="h-5 w-5" />} label="Replies">
            We answer every message by email, at the address you give us.
          </PublicAsideRow>
          {whatsappHref && (
            <PublicAsideRow icon={<WhatsAppGlyph className="h-5 w-5" />} label="WhatsApp">
              <a
                href={whatsappHref}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex min-h-11 items-center font-semibold text-primary underline-offset-2 hover:underline"
              >
                Chat with us on WhatsApp
                <span className="sr-only"> (opens in a new tab)</span>
              </a>
            </PublicAsideRow>
          )}
          {settings?.pickupAddress && (
            <PublicAsideRow icon={<Icon name="location-on" className="h-5 w-5" />} label="Pickup address">
              <span className="whitespace-pre-line">{settings.pickupAddress}</span>
            </PublicAsideRow>
          )}
          {settings?.pickupHours && (
            <PublicAsideRow icon={<Icon name="schedule" className="h-5 w-5" />} label="Pickup hours">
              <span className="whitespace-pre-line">{settings.pickupHours}</span>
            </PublicAsideRow>
          )}
        </ul>
      </PublicAsideCard>
      <PublicAsideCard headingId="contact-custom-heading" title="Have something custom in mind?" tone="plain">
        <p className="font-body text-body-md text-on-surface-variant">
          Tell us about a print that isn&apos;t in the shop and add reference photos or sketches.
        </p>
        <Link href="/bring-your-idea" className={`${buttonLinkClassName("secondary")} mt-6 w-full tablet:w-auto`}>
          Bring your idea
          <Icon name="arrow-forward" className="h-4 w-4" />
        </Link>
      </PublicAsideCard>
    </>
  );
}
