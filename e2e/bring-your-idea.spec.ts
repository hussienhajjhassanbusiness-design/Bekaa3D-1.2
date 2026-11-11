import { test, expect, type Page } from "@playwright/test";
import { E2E_CAPTCHA_TOKEN, routeFakeTurnstile, waitForCaptchaToken } from "./support/fakeTurnstile";
import { stubEmptyCart } from "./support/stubCart";

// Phase 6B-2 — Bring Your Idea against a deterministic stand-in for backend
// 2dfb27b (engagement/api/custom_requests.py, custom_request_admin.py,
// admin_analytics.py): public multipart POST /api/v1/custom-requests, the
// admin pipeline and the funnel. Route interception only: no backend on
// :8000, no media server on :8001.

type Json = Record<string, unknown>;
const uuid = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const ADMIN_ME = { id: "admin-1", email: "admin@example.com", role: "admin", email_verified: true, email_verified_at: "2025-01-01T00:00:00Z", created_at: "2024-01-01T00:00:00Z" };
const CUSTOMER_ME = { ...ADMIN_ME, id: "customer-1", email: "customer@example.com", role: "customer" };
const PNG = Buffer.from("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8ffff3f0005fe02fea7d6a5e00000000049454e44ae426082", "hex");

function problem(status: number, code: string, extra: Json = {}) {
  return { status, contentType: "application/problem+json", body: JSON.stringify({ type: "about:blank", title: "RAW TITLE", status, detail: "RAW DETAIL", code, errors: [], ...extra }) };
}

async function asGuest(page: Page) {
  await page.route(/\/api\/v1\/me$/, (r) => r.fulfill(problem(401, "AUTH_REQUIRED")));
  await page.route(/\/api\/v1\/auth\/refresh$/, (r) => r.fulfill(problem(401, "AUTH_REQUIRED")));
}

async function asUser(page: Page, me: Json) {
  await page.context().addCookies([{ name: "csrf_token", value: "e2e-csrf-value", url: "http://localhost:3000" }]);
  await stubEmptyCart(page);
  await page.route(/\/api\/v1\/me$/, (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(me) }));
}

async function fillIdea(page: Page) {
  await page.getByLabel("Name").fill("Rana Haddad");
  await page.getByLabel("Email").fill("rana@example.com");
  await page.getByLabel("Phone").fill("+961 70 123 456");
  await page.getByLabel("Project title").fill("Cedar lamp");
  await page.getByLabel("Description").fill("A lamp shaped like a cedar.\nAbout 20 cm tall.");
  await page.getByLabel("Preferred colour (optional)").fill("Green");
}

test.describe("Bring Your Idea (Phase 6B-2)", () => {
  test("multipart submit with images: server image refusal names the file, retry without it succeeds", async ({ page }) => {
    await asGuest(page);
    await routeFakeTurnstile(page);
    const bodies: { text: string; contentType: string; csrf: string | undefined }[] = [];
    await page.route(/\/api\/v1\/custom-requests$/, (route) => {
      const r = route.request();
      bodies.push({ text: r.postDataBuffer()?.toString("latin1") ?? "", contentType: r.headers()["content-type"] ?? "", csrf: r.headers()["x-csrf-token"] });
      if (bodies.length === 1) {
        return route.fulfill(problem(422, "UPLOAD_REJECTED", { errors: [{ loc: ["body", "attachments", 1], msg: "RAW MSG", type: "value_error" }] }));
      }
      return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ id: uuid(1), created_at: "2026-11-11T10:00:00Z" }) });
    });

    await page.goto("/bring-your-idea");
    await expect(page.getByRole("heading", { name: "Bring your idea" })).toBeVisible();
    await waitForCaptchaToken(page);
    await fillIdea(page);
    const uploader = page.getByLabel("Reference images (optional)");
    await uploader.setInputFiles([
      { name: "sketch.png", mimeType: "image/png", buffer: PNG },
      { name: "not-really.png", mimeType: "image/png", buffer: Buffer.from("plain text") },
    ]);
    await page.getByRole("button", { name: "Send my idea" }).click();
    await expect(page.getByRole("main").getByRole("alert").first()).toContainText("“not-really.png” couldn't be accepted");
    await expect(page.getByText(/RAW/)).toHaveCount(0);
    const first = bodies[0]!;
    expect(first.contentType).toMatch(/^multipart\/form-data; boundary=/);
    expect(first.csrf).toBeUndefined();
    for (const part of ["name", "email", "phone", "project_title", "description", "preferred_colour", "captcha_token"]) {
      expect(first.text).toContain(`name="${part}"`);
    }
    expect(first.text).not.toContain('name="preferred_material"');
    expect(first.text).toContain(E2E_CAPTCHA_TOKEN);
    expect(first.text).toContain('name="attachments"; filename="sketch.png"');
    expect(first.text).toContain('name="attachments"; filename="not-really.png"');

    await page.getByRole("button", { name: "Remove not-really.png" }).click();
    await waitForCaptchaToken(page);
    await page.getByRole("button", { name: "Send my idea" }).click();
    await expect(page.getByText("we've received your idea")).toBeVisible();
    await expect(page.getByText(uuid(1))).toHaveCount(0);
    expect(bodies[1]!.text).toContain('filename="sketch.png"');
    expect(bodies[1]!.text).not.toContain("not-really.png");
  });

  test("local checks: required fields, non-image file; captcha refusal and scanner outage copy", async ({ page }) => {
    await asGuest(page);
    await routeFakeTurnstile(page);
    let calls = 0;
    await page.route(/\/api\/v1\/custom-requests$/, (route) => {
      calls += 1;
      return route.fulfill(calls === 1 ? problem(400, "CAPTCHA_INVALID") : problem(503, "SERVICE_UNAVAILABLE"));
    });
    await page.goto("/bring-your-idea");
    await waitForCaptchaToken(page);
    await page.getByRole("button", { name: "Send my idea" }).click();
    await expect(page.getByText("Enter a phone number.").first()).toBeVisible();
    await page.getByLabel("Reference images (optional)").setInputFiles({ name: "model.stl", mimeType: "model/stl", buffer: Buffer.from("solid x") });
    await expect(page.getByText('"model.stl" isn\'t a supported file type.')).toBeVisible();
    expect(calls).toBe(0);
    await fillIdea(page);
    await page.getByRole("button", { name: "Send my idea" }).click();
    await expect(page.getByRole("main").getByRole("alert").first()).toContainText("The verification check expired or failed");
    await waitForCaptchaToken(page);
    await page.getByRole("button", { name: "Send my idea" }).click();
    await expect(page.getByRole("main").getByRole("alert").first()).toContainText("We can't accept requests right now");
  });

  test("keyboard and phone-sized viewport", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 });
    await asGuest(page);
    await routeFakeTurnstile(page);
    await page.route(/\/api\/v1\/custom-requests$/, (route) =>
      route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ id: uuid(2), created_at: "2026-11-11T10:00:00Z" }) })
    );
    await page.goto("/bring-your-idea");
    await waitForCaptchaToken(page);
    await page.getByLabel("Name").focus();
    for (const value of ["Karim", "karim@example.com", "70123456", "Bracket", "A wall bracket."]) {
      await page.keyboard.type(value);
      await page.keyboard.press("Tab");
    }
    await expect(page.getByLabel("Description")).toHaveValue("A wall bracket.");
    await page.getByRole("button", { name: "Send my idea" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByText("we've received your idea")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
  });

  test("admin pipeline: funnel, list, detail, quote with CSRF, notes, image download", async ({ page }) => {
    await asUser(page, ADMIN_ME);
    const lead: Json = {
      id: uuid(20), name: "Rana Haddad", email: "rana@example.com", phone: "+961 70 123 456", project_title: "Cedar lamp",
      description: "<script>alert(1)</script>", preferred_material: null, preferred_colour: "Green", dimensions: null,
      status: "contacted", quoted_amount_cents: null, currency: null, outcome: null, admin_notes: null,
      contacted_at: "2026-11-10T11:00:00Z", quoted_at: null, completed_at: null, closed_at: null,
      created_at: "2026-11-10T10:00:00Z", updated_at: "2026-11-10T11:00:00Z",
      attachments: [{ id: uuid(21), original_filename: "sketch.png", mime_type: "image/png", size_bytes: PNG.length, expires_at: "2027-02-08T10:00:00Z", created_at: "2026-11-10T10:00:00Z" }],
    };
    const writes: { path: string; body: unknown; csrf: string | null }[] = [];
    const summary = () => ({ ...lead, attachment_count: 1, description: undefined, attachments: undefined });
    await page.route(/\/api\/v1\/admin\/analytics\/custom-requests\/funnel(\?.*)?$/, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ from: "2026-08-12T00:00:00Z", to: "2026-11-11T00:00:00Z", submitted: 4, contacted: 3, quoted: lead.status === "quoted" ? 2 : 1, won: 0, lost: 1, open: 3, quoted_total_cents: 9000, won_total_cents: 0, currency: "USD" }) })
    );
    await page.route(/\/api\/v1\/admin\/custom-requests(\?.*)?$/, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [summary()], next_cursor: null }) })
    );
    await page.route(/\/api\/v1\/admin\/custom-requests\/[^/?]+$/, (route) => {
      if (route.request().method() === "PATCH") {
        writes.push({ path: new URL(route.request().url()).pathname, body: route.request().postDataJSON(), csrf: route.request().headers()["x-csrf-token"] ?? null });
        Object.assign(lead, route.request().postDataJSON() as Json);
      }
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(lead) });
    });
    await page.route(/\/api\/v1\/admin\/custom-requests\/[^/]+\/transition$/, (route) => {
      const body = route.request().postDataJSON() as Json;
      writes.push({ path: new URL(route.request().url()).pathname, body, csrf: route.request().headers()["x-csrf-token"] ?? null });
      Object.assign(lead, { status: body.target_status, quoted_amount_cents: body.quoted_amount_cents, currency: "USD", quoted_at: "2026-11-11T09:00:00Z" });
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(lead) });
    });
    await page.route(/\/api\/v1\/admin\/custom-requests\/[^/]+\/attachments\/[^/]+\/download$/, (route) =>
      route.fulfill({ status: 200, contentType: "image/png", headers: { "Content-Disposition": "attachment; filename=\"sketch.png\"; filename*=UTF-8''sketch.png" }, body: PNG })
    );

    await page.goto("/admin/custom-requests");
    await expect(page.getByRole("navigation", { name: "Admin" }).getByRole("link", { name: "Bring Your Idea" })).toHaveAttribute("aria-current", "page");
    const funnel = page.getByRole("region", { name: "Funnel" });
    await expect(funnel.getByText("Quoted total")).toBeVisible();
    await expect(funnel.getByText("$90.00")).toBeVisible();
    await page.getByRole("link", { name: "Cedar lamp" }).click();
    await expect(page.getByRole("heading", { name: "Cedar lamp" })).toBeVisible();
    await expect(page.getByText("<script>alert(1)</script>")).toBeVisible();

    await page.getByRole("button", { name: "Record quote" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel(/Quoted amount/).fill("125.50");
    await dialog.getByRole("button", { name: "Record quote" }).click();
    await expect(dialog).toBeHidden();
    await expect(page.getByRole("region", { name: "Pipeline" }).getByText("$125.50")).toBeVisible();
    await expect(page.getByRole("button", { name: "Start work (won)" })).toBeVisible();

    await page.getByLabel(/Internal note/).fill("Quoted by phone.");
    await page.getByRole("region", { name: "Notes" }).getByRole("button", { name: "Save" }).click();
    await expect(page.getByText("Notes saved.")).toBeVisible();
    expect(writes).toEqual([
      { path: `/api/v1/admin/custom-requests/${uuid(20)}/transition`, body: { target_status: "quoted", quoted_amount_cents: 12550 }, csrf: "e2e-csrf-value" },
      { path: `/api/v1/admin/custom-requests/${uuid(20)}`, body: { admin_notes: "Quoted by phone." }, csrf: "e2e-csrf-value" },
    ]);

    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download sketch.png" }).click();
    expect((await download).suggestedFilename()).toBe("sketch.png");
  });

  test("a signed-in customer gets the normal 404 on the admin pipeline", async ({ page }) => {
    await asUser(page, CUSTOMER_ME);
    let adminCalls = 0;
    await page.route(/\/api\/v1\/admin\//, (route) => {
      adminCalls += 1;
      return route.fulfill(problem(404, "NOT_FOUND"));
    });
    await page.goto(`/admin/custom-requests/${uuid(20)}`);
    await expect(page.getByText(/page not found/i)).toBeVisible();
    expect(adminCalls).toBe(0);
  });
});
