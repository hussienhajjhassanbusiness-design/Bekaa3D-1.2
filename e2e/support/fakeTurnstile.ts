import type { Page } from "@playwright/test";

// Mocked-E2E stand-in for Cloudflare's Turnstile script. It serves a tiny
// script in place of challenges.cloudflare.com/turnstile/v0/api.js that
// behaves like the public always-pass test site key: render() immediately
// issues the dummy token. Mocked E2E stays offline and deterministic.
// This is NOT real-backend acceptance.
export const E2E_CAPTCHA_TOKEN = "XXXX.DUMMY.TOKEN.XXXX";

const FAKE_TURNSTILE_SCRIPT = `
(function () {
  var n = 0;
  var widgets = {};
  window.turnstile = {
    render: function (el, opts) {
      var id = "w" + (++n);
      widgets[id] = opts;
      setTimeout(function () { opts.callback(${JSON.stringify(E2E_CAPTCHA_TOKEN)}); }, 0);
      return id;
    },
    reset: function (id) {
      var opts = widgets[id];
      if (opts) setTimeout(function () { opts.callback(${JSON.stringify(E2E_CAPTCHA_TOKEN)}); }, 0);
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
