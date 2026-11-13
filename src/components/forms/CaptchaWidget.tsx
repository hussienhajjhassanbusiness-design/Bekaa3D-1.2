"use client";

import { useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import { loadTurnstile, type TurnstileApi } from "@/lib/captcha/turnstileLoader";

// The one captcha primitive for every captcha-gated form (register,
// resend verification, password-reset request today; Contact and Bring
// Your Idea through their existing `captchaSlot` seam later). Provider is
// Cloudflare Turnstile (backend ADR-025). The parent owns the token: this
// widget reports it through onToken (null when cleared/expired/errored)
// and exposes reset(), because a Turnstile token is single-use and must be
// re-issued after every submission attempt.

export interface CaptchaWidgetHandle {
  reset: () => void;
}

export interface CaptchaWidgetProps {
  siteKey: string | null;
  onToken: (token: string | null) => void;
  ref?: Ref<CaptchaWidgetHandle>;
  // Presentation only (redesign Batch 4). "center" centres the provider's
  // fixed 300px frame inside an auth card. A centring flex container
  // overflows equally on both sides, so at 320px the frame spills 6px into
  // the card padding on each side instead of being clipped or pushing the
  // page wider. Default "start" keeps Contact / Bring Your Idea unchanged.
  align?: "start" | "center";
}

const LOAD_FAILURE_MESSAGE = "Verification couldn't load. Please refresh the page and try again.";
const NOT_CONFIGURED_MESSAGE = "Verification is unavailable right now. Please try again later.";

export function CaptchaWidget({ siteKey, onToken, ref, align = "start" }: CaptchaWidgetProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const apiRef = useRef<TurnstileApi | null>(null);
  const widgetIdRef = useRef<string | null>(null);
  const onTokenRef = useRef(onToken);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    onTokenRef.current = onToken;
  }, [onToken]);

  useImperativeHandle(
    ref,
    () => ({
      reset() {
        onTokenRef.current(null);
        if (apiRef.current && widgetIdRef.current) {
          apiRef.current.reset(widgetIdRef.current);
        }
      },
    }),
    []
  );

  useEffect(() => {
    if (!siteKey) {
      return;
    }
    let cancelled = false;
    loadTurnstile().then(
      (api) => {
        if (cancelled || !containerRef.current) {
          return;
        }
        apiRef.current = api;
        widgetIdRef.current =
          api.render(containerRef.current, {
            sitekey: siteKey,
            callback: (token) => {
              setFailed(false);
              onTokenRef.current(token);
            },
            "expired-callback": () => onTokenRef.current(null),
            "error-callback": () => {
              onTokenRef.current(null);
              setFailed(true);
            },
          }) ?? null;
      },
      () => {
        if (!cancelled) {
          setFailed(true);
        }
      }
    );
    return () => {
      cancelled = true;
      if (apiRef.current && widgetIdRef.current) {
        apiRef.current.remove(widgetIdRef.current);
      }
      widgetIdRef.current = null;
    };
  }, [siteKey]);

  if (!siteKey) {
    return (
      <p
        role="alert"
        className={`mt-4 text-caption text-danger ${align === "center" ? "text-center" : ""}`}
      >
        {NOT_CONFIGURED_MESSAGE}
      </p>
    );
  }

  return (
    <div className="mt-4">
      <div className={align === "center" ? "flex justify-center" : undefined}>
        <div ref={containerRef} data-testid="captcha-widget" />
      </div>
      {failed && (
        <p role="alert" className={`mt-2 text-caption text-danger ${align === "center" ? "text-center" : ""}`}>
          {LOAD_FAILURE_MESSAGE}
        </p>
      )}
    </div>
  );
}
