import { test, expect, type Page, type Route } from "@playwright/test";
import { stubEmptyCart } from "./support/stubCart";
import { E2E_ORIGIN } from "./support/origin";

// Phase 5C: keep the header cart read inside the browser (no :8000).
test.beforeEach(async ({ page }) => {
  await stubEmptyCart(page);
});

// Phase 5B — /account/addresses (FVS-023) against a deterministic,
// in-memory stand-in for the real contract (openapi.json
// /api/v1/me/addresses*, backend 2dfb27b). Route interception only:
// no backend on :8000 and no media server on :8001 are needed. The fake
// keeps state for the whole test (so a reload "persists"), applies the
// backend's own default rules (first address is the default; PUT
// …/default clears the previous one; deleting the default leaves none),
// and refuses any write without the matching X-CSRF-Token header.

const CSRF = "e2e-csrf-value";

const ME = {
  id: "u-1",
  email: "ada@example.com",
  role: "customer",
  email_verified: true,
  email_verified_at: "2025-01-01T00:00:00Z",
  created_at: "2024-01-01T00:00:00Z",
};

interface StoredAddress {
  id: string;
  label: string;
  recipient_name: string;
  phone: string;
  governorate: string;
  city: string;
  area: string | null;
  street: string | null;
  landmark_notes: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

interface FakeBackend {
  addresses: StoredAddress[];
  writes: { method: string; path: string; csrf: string | undefined; body: unknown }[];
  failNextCreateWithPhone422: boolean;
}

const NOW = "2026-11-10T10:00:00Z";

function problem(route: Route, status: number, code: string, errors: unknown[] = []) {
  return route.fulfill({
    status,
    contentType: "application/problem+json",
    body: JSON.stringify({ type: "about:blank", title: "RAW TITLE", status, detail: "RAW DETAIL", code, errors }),
  });
}

function ordered(addresses: StoredAddress[]) {
  return [...addresses].sort((a, b) => Number(b.is_default) - Number(a.is_default));
}

async function installFakeBackend(page: Page, initial: StoredAddress[] = []): Promise<FakeBackend> {
  const backend: FakeBackend = { addresses: [...initial], writes: [], failNextCreateWithPhone422: false };
  let nextId = 1;

  await page.context().addCookies([{ name: "csrf_token", value: CSRF, url: E2E_ORIGIN }]);
  await page.route("**/api/v1/me", (route) => route.fulfill({ status: 200, body: JSON.stringify(ME) }));

  await page.route(/\/api\/v1\/me\/addresses(\/.*)?$/, async (route) => {
    const request = route.request();
    const method = request.method();
    const path = new URL(request.url()).pathname;
    const match = path.match(/^\/api\/v1\/me\/addresses(?:\/([^/]+))?(\/default)?$/);
    const id = match?.[1] ? decodeURIComponent(match[1]) : undefined;
    const isDefaultRoute = Boolean(match?.[2]);

    if (method === "GET") {
      if (!id) {
        return route.fulfill({ status: 200, body: JSON.stringify({ items: ordered(backend.addresses) }) });
      }
      const found = backend.addresses.find((address) => address.id === id);
      return found ? route.fulfill({ status: 200, body: JSON.stringify(found) }) : problem(route, 404, "NOT_FOUND");
    }

    const body = request.postData() ? request.postDataJSON() : undefined;
    const csrf = request.headers()["x-csrf-token"];
    backend.writes.push({ method, path, csrf, body });
    if (csrf !== CSRF) {
      return problem(route, 403, "CSRF_INVALID");
    }

    if (method === "POST" && !id) {
      if (backend.failNextCreateWithPhone422) {
        backend.failNextCreateWithPhone422 = false;
        return problem(route, 422, "VALIDATION_ERROR", [
          { loc: ["body", "phone"], msg: "invalid value", type: "value_error" },
        ]);
      }
      const makeDefault = backend.addresses.length === 0 || body.is_default === true;
      if (makeDefault) {
        backend.addresses.forEach((address) => (address.is_default = false));
      }
      const created: StoredAddress = {
        id: `addr-${nextId++}`,
        label: body.label,
        recipient_name: body.recipient_name,
        phone: "+96171123456",
        governorate: body.governorate,
        city: body.city,
        area: body.area ?? null,
        street: body.street ?? null,
        landmark_notes: body.landmark_notes,
        is_default: makeDefault,
        created_at: NOW,
        updated_at: NOW,
      };
      backend.addresses.push(created);
      return route.fulfill({ status: 201, body: JSON.stringify(created) });
    }

    const target = backend.addresses.find((address) => address.id === id);
    if (!target) {
      return problem(route, 404, "NOT_FOUND");
    }

    if (method === "PUT" && isDefaultRoute) {
      backend.addresses.forEach((address) => (address.is_default = address.id === id));
      return route.fulfill({ status: 200, body: JSON.stringify(target) });
    }
    if (method === "PATCH") {
      const { is_default: isDefault, ...details } = body as Record<string, unknown>;
      Object.assign(target, details);
      if (isDefault === true) {
        backend.addresses.forEach((address) => (address.is_default = address.id === id));
      } else if (isDefault === false) {
        target.is_default = false;
      }
      return route.fulfill({ status: 200, body: JSON.stringify(target) });
    }
    if (method === "DELETE") {
      backend.addresses = backend.addresses.filter((address) => address.id !== id);
      return route.fulfill({ status: 204, body: "" });
    }
    return problem(route, 405, "METHOD_NOT_ALLOWED");
  });

  return backend;
}

async function fillAddress(page: Page, values: { label: string; city: string; governorate: string }) {
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(/^label/i).fill(values.label);
  await dialog.getByLabel(/recipient name/i).fill("Jane Doe");
  await dialog.getByLabel(/^phone/i).fill("71 123 456");
  await dialog.getByLabel(/governorate/i).selectOption(values.governorate);
  await dialog.getByLabel(/^city/i).fill(values.city);
  await dialog.getByLabel(/landmark notes/i).fill("Blue gate next to the bakery");
}

test.describe("Account address book (Phase 5B / FVS-023)", () => {
  test("an anonymous visit redirects to /login with a safe returnTo", async ({ page }) => {
    await page.goto("/account/addresses");
    await expect(page).toHaveURL(/\/login\?returnTo=%2Faccount%2Faddresses$/);
  });

  test("the account nav links to Addresses and marks it current", async ({ page }) => {
    await installFakeBackend(page);
    await page.goto("/account/profile");

    await page.getByRole("navigation", { name: "Account" }).getByRole("link", { name: "Addresses" }).click();

    await expect(page).toHaveURL(/\/account\/addresses$/);
    await expect(page.getByRole("link", { name: "Addresses" })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("heading", { level: 1, name: "Addresses" })).toBeVisible();
  });

  test("create → reload persists → edit → reload persists → set default → delete → reload gone, every write with CSRF", async ({
    page,
  }) => {
    const backend = await installFakeBackend(page);
    await page.goto("/account/addresses");

    // Empty state → first address (automatically the default).
    await expect(page.getByText(/no saved addresses/i)).toBeVisible();
    await page.getByRole("button", { name: /add an address/i }).click();
    await expect(page.getByRole("dialog").getByRole("checkbox")).toHaveCount(0);
    await fillAddress(page, { label: "Home", city: "Beirut", governorate: "beirut" });
    await page.getByRole("button", { name: "Save address" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByText("Address saved.")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();

    await page.reload();
    const home = page.getByRole("article", { name: "Home" });
    await expect(home).toBeVisible();
    await expect(home.getByText("Default", { exact: true })).toBeVisible();

    // Second address, not default.
    await page.getByRole("button", { name: "Add address" }).click();
    await fillAddress(page, { label: "Work", city: "Tripoli", governorate: "north" });
    await page.getByRole("button", { name: "Save address" }).click();
    await expect(page.getByRole("article", { name: "Work" })).toBeVisible();

    // Edit: only the changed fields are sent.
    await page.getByRole("button", { name: "Edit Work" }).click();
    await page.getByRole("dialog").getByLabel(/^city/i).fill("Batroun");
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByText("Address updated.")).toBeVisible();
    await page.reload();
    await expect(page.getByRole("article", { name: "Work" }).getByText("Batroun, North")).toBeVisible();
    const patch = backend.writes.find((write) => write.method === "PATCH");
    expect(patch?.body).toEqual({ city: "Batroun" });

    // Default switch is server-authoritative.
    await page.getByRole("button", { name: "Set as default: Work" }).click();
    await expect(page.getByText("Default address updated.")).toBeVisible();
    await expect(page.getByRole("article", { name: "Work" }).getByText("Default", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Set as default: Home" })).toBeVisible();

    // Delete with confirmation; Cancel first sends nothing.
    await page.getByRole("button", { name: "Delete Home" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();
    expect(backend.writes.filter((write) => write.method === "DELETE")).toHaveLength(0);
    await page.getByRole("button", { name: "Delete Home" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Delete address" }).click();
    await expect(page.getByText("Address deleted.")).toBeVisible();
    await page.reload();
    await expect(page.getByRole("article", { name: "Work" })).toBeVisible();
    await expect(page.getByRole("article", { name: "Home" })).toHaveCount(0);

    expect(backend.writes.map((write) => write.method)).toEqual(["POST", "POST", "PATCH", "PUT", "DELETE"]);
    for (const write of backend.writes) {
      expect(write.csrf).toBe(CSRF);
    }
    await expect(page.getByText(/RAW|zone|shipping fee/i)).toHaveCount(0);
  });

  test("a server 422 on phone is shown on the phone field with frontend copy, never the raw message", async ({ page }) => {
    const backend = await installFakeBackend(page);
    backend.failNextCreateWithPhone422 = true;
    await page.goto("/account/addresses");

    await page.getByRole("button", { name: /add an address/i }).click();
    await fillAddress(page, { label: "Home", city: "Beirut", governorate: "beirut" });
    await page.getByRole("button", { name: "Save address" }).click();

    const dialog = page.getByRole("dialog");
    const phone = dialog.getByLabel(/^phone/i);
    await expect(dialog.getByText(/enter a lebanese phone number/i)).toBeVisible();
    await expect(phone).toHaveAttribute("aria-invalid", "true");
    await expect(phone).toBeFocused();
    await expect(page.getByText(/invalid value|RAW/)).toHaveCount(0);
  });

  test("client validation blocks an incomplete form without any request", async ({ page }) => {
    const backend = await installFakeBackend(page);
    await page.goto("/account/addresses");

    await page.getByRole("button", { name: /add an address/i }).click();
    await page.getByRole("button", { name: "Save address" }).click();

    await expect(page.getByRole("dialog").getByText("Choose a governorate.")).toBeVisible();
    await expect(page.getByRole("dialog").getByLabel(/^label/i)).toBeFocused();
    expect(backend.writes).toHaveLength(0);
  });

  test("keyboard: the dialog opens focused on the first field, Escape closes it and returns focus", async ({ page }) => {
    await installFakeBackend(page);
    await page.goto("/account/addresses");

    const trigger = page.getByRole("button", { name: /add an address/i });
    await trigger.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("dialog").getByLabel(/^label/i)).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(trigger).toBeFocused();
  });

  for (const width of [320, 375, 768, 1440]) {
    test(`no horizontal overflow at ${width}px, list and open form`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await installFakeBackend(page, [
        {
          id: "addr-9",
          label: "A rather long address label for wrapping",
          recipient_name: "Jane Doe",
          phone: "+9613123456",
          governorate: "keserwan_jbeil",
          city: "Jounieh",
          area: "Kaslik",
          street: "A street name that is long enough to need wrapping on a phone",
          landmark_notes: "Blue gate next to the bakery, third floor",
          is_default: true,
          created_at: NOW,
          updated_at: NOW,
        },
      ]);
      await page.goto("/account/addresses");
      await expect(page.getByRole("button", { name: /^Edit /i })).toBeVisible();

      const overflow = () =>
        page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(await overflow()).toBeLessThanOrEqual(0);

      await page.getByRole("button", { name: "Add address" }).click();
      await expect(page.getByRole("dialog")).toBeVisible();
      expect(await overflow()).toBeLessThanOrEqual(0);
      const box = await page.getByRole("dialog").boundingBox();
      expect(box!.width).toBeLessThanOrEqual(width);
    });
  }
});
