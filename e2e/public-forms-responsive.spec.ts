import { test, expect, type Page } from "@playwright/test";
import { stubEmptyCart } from "./support/stubCart";
import { stubGuest } from "./support/stubGuest";
import { routeFakeTurnstile, waitForCaptchaToken } from "./support/fakeTurnstile";

// Redesign Batch 8 — the public Contact and Bring Your Idea pages at the six
// QA widths: one visible h1 clear of the sticky header, no horizontal overflow
// with long validation messages, long file names and a 300px captcha frame,
// the success receipt, and only real channel information (from public
// settings). Route interception only; no backend.

const WIDTHS = [320, 375, 768, 1024, 1280, 1440];
const PNG = Buffer.from(
  "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8ffff3f0005fe02fea7d6a5e00000000049454e44ae426082",
  "hex"
);
const LONG_NAME = `reference-sketch-${"very-long-segment-".repeat(6)}final.png`;

const SETTINGS = {
  accepting_orders: true,
  cash_payment_enabled: true,
  cash_max_order_total: { amount_cents: 50000, currency: "USD" },
  pickup_address: "Workshop pickup, Main Street, Zahle",
  pickup_hours: null,
  whatsapp_number: "+96170000000",
};

test.beforeEach(async ({ page }) => {
  await stubEmptyCart(page);
  await stubGuest(page);
  await routeFakeTurnstile(page);
  await page.route(/\/api\/v1\/settings\/public$/, (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(SETTINGS) })
  );
});

async function simulateRealCaptchaFrame(page: Page) {
  await waitForCaptchaToken(page);
  await page.evaluate(() => {
    const container = document.querySelector('[data-testid="captcha-widget"]');
    if (container?.querySelector('[data-e2e-frame="true"]')) return;
    const frame = document.createElement("div");
    frame.setAttribute("data-e2e-frame", "true");
    frame.style.width = "300px";
    frame.style.height = "65px";
    container?.appendChild(frame);
  });
}

async function expectNoOverflow(page: Page, width: number, label: string) {
  const [scrollWidth, clientWidth] = await page.evaluate(() => [
    document.documentElement.scrollWidth,
    document.documentElement.clientWidth,
  ]);
  expect(scrollWidth, `${width}px ${label}: horizontal overflow`).toBeLessThanOrEqual(clientWidth);
}

async function expectH1(page: Page, name: RegExp, width: number) {
  const heading = page.getByRole("heading", { level: 1 });
  await expect(heading).toHaveCount(1);
  await expect(heading).toHaveText(name);
  expect((await heading.boundingBox())!.y, `${width}px: h1 under the sticky header`).toBeGreaterThanOrEqual(64);
}

async function expectCaptchaFits(page: Page, width: number) {
  await simulateRealCaptchaFrame(page);
  const frame = (await page.locator('[data-e2e-frame="true"]').boundingBox())!;
  expect(frame.x, `${width}px: captcha clipped left`).toBeGreaterThanOrEqual(0);
  expect(frame.x + frame.width, `${width}px: captcha clipped right`).toBeLessThanOrEqual(width);
}

test("/contact fits every width with validation errors, captcha and real channels only", async ({ page }) => {
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/contact");
    await expectH1(page, /contact us/i, width);
    await expectCaptchaFits(page, width);

    const channels = page.getByRole("region", { name: "Other ways to reach us" });
    await expect(channels.getByRole("link", { name: /whatsapp/i })).toBeVisible();
    await expect(channels.getByText("Workshop pickup, Main Street, Zahle")).toBeVisible();
    // Unconfigured pickup hours render nothing — never a guessed value.
    await expect(channels.getByText("Pickup hours")).toHaveCount(0);

    await page.getByLabel("Name").fill("A".repeat(100));
    await page.getByLabel("Phone (optional)").fill("not a phone");
    await page.getByRole("button", { name: "Send message" }).click();
    await expect(page.getByText("Enter a valid phone number.").first()).toBeVisible();
    await expectNoOverflow(page, width, "contact with errors");

    const submit = (await page.getByRole("button", { name: "Send message" }).boundingBox())!;
    expect(submit.height, `${width}px: submit target`).toBeGreaterThanOrEqual(44);
  }
});

test("/bring-your-idea fits every width with long file names, upload errors and the success receipt", async ({
  page,
}) => {
  await page.route(/\/api\/v1\/custom-requests$/, (r) =>
    r.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "secret-receipt-id", created_at: "2026-11-11T10:00:00Z" }),
    })
  );
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/bring-your-idea");
    await expectH1(page, /bring your idea/i, width);
    await expectCaptchaFits(page, width);

    const uploader = page.getByLabel("Reference images (optional)");
    await uploader.setInputFiles([
      { name: LONG_NAME, mimeType: "image/png", buffer: PNG },
      { name: "second.webp", mimeType: "image/webp", buffer: PNG },
      { name: "model.stl", mimeType: "model/stl", buffer: Buffer.from("solid x") },
    ]);
    await expect(page.getByText('"model.stl" isn\'t a supported file type.')).toBeVisible();
    await expect(page.getByRole("button", { name: `Remove ${LONG_NAME}` })).toBeVisible();
    const remove = (await page.getByRole("button", { name: "Remove second.webp" }).boundingBox())!;
    expect(remove.height, `${width}px: remove target`).toBeGreaterThanOrEqual(44);
    expect(remove.x + remove.width, `${width}px: remove button clipped`).toBeLessThanOrEqual(width);
    await expectNoOverflow(page, width, "byi with files");
  }

  // Success receipt at the narrowest width.
  await page.setViewportSize({ width: 320, height: 900 });
  await page.goto("/bring-your-idea");
  await page.getByLabel("Name").fill("Rana Haddad");
  await page.getByLabel("Email").fill("rana@example.com");
  await page.getByLabel("Phone").fill("+961 70 123 456");
  await page.getByLabel("Project title").fill("Cedar lamp");
  await page.getByLabel("Description").fill("A lamp shaped like a cedar.");
  await waitForCaptchaToken(page);
  await page.getByRole("button", { name: "Send my idea" }).click();
  await expect(page.getByText("we've received your idea")).toBeVisible();
  await expect(page.getByText("secret-receipt-id")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Send another idea" })).toBeVisible();
  await expectNoOverflow(page, 320, "byi success");
});

test("the dropzone is keyboard reachable through the native file input", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 900 });
  await page.goto("/bring-your-idea");
  await page.getByLabel("Dimensions (optional)").focus();
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Reference images (optional)")).toBeFocused();
  const ring = await page.getByTestId("file-dropzone").evaluate((el) => getComputedStyle(el).boxShadow);
  expect(ring).not.toBe("none");
});
