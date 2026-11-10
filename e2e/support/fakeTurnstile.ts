import { expect, type Page } from "@playwright/test";

// Mocked-E2E stand-in for Cloudflare's Turnstile script. It serves a tiny
// script in place of challenges.cloudflare.com/turnstile/v0/api.js that
// behaves like the public always-pass test site key: render() immediately
// issues the dummy token. Mocked E2E stays offline and deterministic.
// This is NOT real-backend acceptance.
export const E2E_CAPTCHA_TOKEN = "XXXX.DUMMY.TOKEN.XXXX";

// Set by the fake script on the widget container once the token has been
// handed to the app's onToken callback. Test-support only — the app never
// reads it.
const TOKEN_ISSUED_ATTRIBUTE = "data-e2e-captcha-token-issued";

const FAKE_TURNSTILE_SCRIPT = `
(function () {
  var n = 0;
  var widgets = {};
  var ISSUED_ATTR = ${JSON.stringify(TOKEN_ISSUED_ATTRIBUTE)};
  // Delivers the token asynchronously (like the real widget), then marks
  // the container so a test can wait for "token issued" deterministically
  // instead of racing the submit click against this callback.
  function issue(id) {
    setTimeout(function () {
      var w = widgets[id];
      if (!w) return;
      w.opts.callback(${JSON.stringify(E2E_CAPTCHA_TOKEN)});
      w.el.setAttribute(ISSUED_ATTR, "true");
    }, 0);
  }
  window.turnstile = {
    render: function (el, opts) {
      var id = "w" + (++n);
      widgets[id] = { el: el, opts: opts };
      issue(id);
      return id;
    },
    reset: function (id) {
      var w = widgets[id];
      if (!w) return;
      w.el.removeAttribute(ISSUED_ATTR);
      issue(id);
    },
    remove: function (id) { delete widgets[id]; }
  };
})();
`;

export async function routeFakeTurnstile(page: Page) {
  await page.route("https://challenges.cloudflare.com/turnstile/**", (route) =>
    route.fulfill({ status: 200, contentType: "application/javascript", body: FAKE_TURNSTILE_SCRIPT })
  );
}

// Waits until the fake widget has issued its token to the form. A submit
// clicked before this point is (correctly) rejected client-side with the
// "Please complete the verification" message and never reaches the mocked
// endpoint — under full-suite load that race was losable.
export async function waitForCaptchaToken(page: Page) {
  await expect(page.locator(`[data-testid="captcha-widget"][${TOKEN_ISSUED_ATTRIBUTE}="true"]`)).toBeAttached();
}
