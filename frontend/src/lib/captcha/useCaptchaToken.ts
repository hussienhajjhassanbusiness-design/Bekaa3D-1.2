"use client";

import { useCallback, useRef, useState } from "react";
import type { CaptchaWidgetHandle } from "@/components/forms/CaptchaWidget";
import { getTurnstileSiteKey } from "./turnstileConfig";

// Page-side state for the single CaptchaWidget primitive: the current
// single-use token, the widget handle, and reset(). Call reset() after
// every submission attempt so the next attempt carries a fresh token.
export function useCaptchaToken() {
  const siteKey = getTurnstileSiteKey();
  const widgetRef = useRef<CaptchaWidgetHandle>(null);
  const [token, setToken] = useState<string | null>(null);
  const reset = useCallback(() => {
    widgetRef.current?.reset();
  }, []);
  return { siteKey, widgetRef, token, onToken: setToken, reset };
}
