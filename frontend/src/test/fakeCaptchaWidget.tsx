import { useEffect, useImperativeHandle, useRef } from "react";
import type { CaptchaWidgetProps } from "@/components/forms/CaptchaWidget";

// Test double for CaptchaWidget used by page tests (vi.mock the module and
// return this). By default it behaves like Cloudflare's always-pass test
// site key: it issues a token on mount and a fresh one after every reset.
// Set fakeCaptcha.autoIssue = false to simulate an unsolved challenge.
export const FAKE_CAPTCHA_TOKEN = "XXXX.DUMMY.TOKEN.XXXX";

export const fakeCaptcha = {
  autoIssue: true,
  resetCount: 0,
  issueCount: 0,
};

export function resetFakeCaptcha() {
  fakeCaptcha.autoIssue = true;
  fakeCaptcha.resetCount = 0;
  fakeCaptcha.issueCount = 0;
}

export function FakeCaptchaWidget({ onToken, ref }: CaptchaWidgetProps) {
  const onTokenRef = useRef(onToken);
  useEffect(() => {
    onTokenRef.current = onToken;
  }, [onToken]);

  useImperativeHandle(
    ref,
    () => ({
      reset() {
        fakeCaptcha.resetCount += 1;
        onTokenRef.current(null);
        if (fakeCaptcha.autoIssue) {
          fakeCaptcha.issueCount += 1;
          onTokenRef.current(FAKE_CAPTCHA_TOKEN);
        }
      },
    }),
    []
  );

  useEffect(() => {
    if (fakeCaptcha.autoIssue) {
      fakeCaptcha.issueCount += 1;
      onTokenRef.current(FAKE_CAPTCHA_TOKEN);
    }
  }, []);

  return <div data-testid="captcha-widget" />;
}
