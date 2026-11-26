import { test, expect, type Page, type Route } from "@playwright/test";
import { E2E_ORIGIN } from "./support/origin";

// Admin → Categories lifecycle: Active / Disabled / Archived tabs, enable and
// disable, archive with confirmation. A deterministic in-memory stand-in for
// the real contract (backend docs/reference-data.md): DELETE archives (soft,
// terminal, refused with 409 CATEGORY_IN_USE while a live product uses the
// category), PATCH toggles is_active and answers 409 on an archived row, and
// there is no restore endpoint.

const CSRF = "e2e-csrf-value";
const ADMIN = {
  id: "admin-1",
  email: "admin@example.com",
  role: "admin",
  email_verified: true,
  email_verified_at: "2025-01-01T00:00:00Z",
  created_at: "2024-01-01T00:00:00Z",
};

interface Category {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
  deleted_at: string | null;
  inUse: boolean;
}

interface Fake {
  categories: Category[];
  writes: { method: string; path: string; body: unknown; csrf: string | undefined }[];
}

function detail(c: Category) {
  return {
    id: c.id,
    name: c.name,
    slug: c.slug,
    is_active: c.is_active,
    deleted_at: c.deleted_at,
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-01T00:00:00Z",
  };
}

async function install(page: Page): Promise<Fake> {
  const fake: Fake = {
    categories: [
      { id: "c1", name: "Toys", slug: "toys", is_active: true, deleted_at: null, inUse: true },
      { id: "c2", name: "Seasonal", slug: "seasonal", is_active: true, deleted_at: null, inUse: false },
      { id: "c3", name: "Decor", slug: "decor", is_active: false, deleted_at: null, inUse: false },
      {
        id: "c4",
        name: "Old range",
        slug: "old-range",
        is_active: false,
        deleted_at: "2026-11-02T00:00:00Z",
        inUse: false,
      },
    ],
    writes: [],
  };
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  const problem = (route: Route, status: number, code: string) =>
    json(route, { type: "about:blank", title: code, status, code }, status);

  await page.context().addCookies([{ name: "csrf_token", value: CSRF, url: E2E_ORIGIN }]);
  await page.route(/\/api\/v1\/me$/, (r) => json(r, ADMIN));
  await page.route(/\/api\/v1\/notifications(\?.*)?$/, (r) => json(r, { items: [], next_cursor: null }));
  await page.route(/\/api\/v1\/me\/notifications(\?.*)?$/, (r) => json(r, { items: [], next_cursor: null }));
  await page.route(/\/api\/v1\/admin\/categories(\?.*)?$/, (route) => {
    const includeDeleted = new URL(route.request().url()).searchParams.get("include_deleted") === "true";
    const items = fake.categories.filter((c) => includeDeleted || c.deleted_at === null).map(detail);
    return json(route, { items, next_cursor: null });
  });
  await page.route(/\/api\/v1\/admin\/categories\/[^/?]+$/, (route) => {
    const request = route.request();
    const id = new URL(request.url()).pathname.split("/").pop()!;
    const category = fake.categories.find((c) => c.id === id);
    const body = request.postData() ? request.postDataJSON() : null;
    fake.writes.push({
      method: request.method(),
      path: new URL(request.url()).pathname,
      body,
      csrf: request.headers()["x-csrf-token"],
    });
    if (!category) return problem(route, 404, "NOT_FOUND");
    if (category.deleted_at !== null) return problem(route, 409, "INVALID_STATE_TRANSITION");
    if (request.method() === "PATCH") {
      if (typeof body?.is_active === "boolean") category.is_active = body.is_active;
      if (typeof body?.name === "string") category.name = body.name;
      return json(route, detail(category));
    }
    if (request.method() === "DELETE") {
      if (category.inUse) return problem(route, 409, "CATEGORY_IN_USE");
      category.deleted_at = "2026-11-26T12:00:00Z";
      category.is_active = false;
      return route.fulfill({ status: 204, body: "" });
    }
    return problem(route, 405, "METHOD_NOT_ALLOWED");
  });
  return fake;
}

const tab = (page: Page, name: RegExp) => page.getByRole("tab", { name });

test.describe("Admin categories lifecycle", () => {
  test("tabs with counts; disable, enable and archive move categories between them", async ({ page }) => {
    const fake = await install(page);
    await page.goto("/admin/categories");

    await expect(tab(page, /^Active/)).toHaveAttribute("aria-selected", "true");
    await expect(tab(page, /^Active/)).toHaveAccessibleName("Active, 2 categories");
    await expect(tab(page, /^Disabled/)).toHaveAccessibleName("Disabled, 1 category");
    await expect(tab(page, /^Archived/)).toHaveAccessibleName("Archived, 1 category");
    await expect(tab(page, /^Active/)).toContainText("Active (2)");

    // Disable → Disabled tab.
    await page.getByRole("button", { name: "Disable Seasonal" }).click();
    await expect(page.getByRole("status").filter({ hasText: "“Seasonal” was disabled." })).toBeVisible();
    await expect(tab(page, /^Disabled/)).toHaveAccessibleName("Disabled, 2 categories");
    await tab(page, /^Disabled/).click();
    const panel = page.getByRole("tabpanel");
    await expect(panel.getByText("Seasonal", { exact: true })).toBeVisible();

    // Archive from Disabled, with confirmation → Archived tab.
    await page.getByRole("button", { name: "Archive Seasonal" }).click();
    const dialog = page.getByRole("dialog", { name: "Archive “Seasonal”?" });
    await expect(dialog).toContainText("slug is released");
    await expect(dialog).toContainText("can't be edited, enabled or restored");
    await dialog.getByRole("button", { name: "Archive" }).click();
    await expect(dialog).toBeHidden();
    await expect(page.getByRole("status").filter({ hasText: "“Seasonal” was archived." })).toBeVisible();
    await expect(tab(page, /^Archived/)).toHaveAccessibleName("Archived, 2 categories");
    await tab(page, /^Archived/).click();
    await expect(panel.getByText("Seasonal", { exact: true })).toBeVisible();
    await expect(panel.getByRole("button")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /restore/i })).toHaveCount(0);

    // Enable the remaining disabled one → Active.
    await tab(page, /^Disabled/).click();
    await page.getByRole("button", { name: "Enable Decor" }).click();
    await expect(tab(page, /^Active/)).toHaveAccessibleName("Active, 2 categories");

    expect(fake.writes.map((w) => `${w.method} ${w.path} ${JSON.stringify(w.body)} ${w.csrf}`)).toEqual([
      `PATCH /api/v1/admin/categories/c2 {"is_active":false} ${CSRF}`,
      `DELETE /api/v1/admin/categories/c2 null ${CSRF}`,
      `PATCH /api/v1/admin/categories/c3 {"is_active":true} ${CSRF}`,
    ]);
  });

  test("archiving a category still used by a product is refused safely and nothing changes", async ({ page }) => {
    const fake = await install(page);
    await page.goto("/admin/categories");

    await page.getByRole("button", { name: "Archive Toys" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Archive" }).click();
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(page.getByRole("alert").filter({ hasText: "still used by a live product" })).toBeVisible();
    await expect(page.getByText(/was archived/)).toHaveCount(0);
    await expect(page.getByRole("tabpanel").getByText("Toys", { exact: true })).toBeVisible();
    await expect(tab(page, /^Archived/)).toHaveAccessibleName("Archived, 1 category");
    expect(fake.categories.find((c) => c.id === "c1")!.deleted_at).toBeNull();
  });

  test("keyboard: tabs move with the arrow keys and the dialog can be cancelled", async ({ page }) => {
    const fake = await install(page);
    await page.goto("/admin/categories");

    await tab(page, /^Active/).focus();
    await page.keyboard.press("ArrowRight");
    await expect(tab(page, /^Disabled/)).toBeFocused();
    await expect(tab(page, /^Disabled/)).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("End");
    await expect(tab(page, /^Archived/)).toBeFocused();
    await page.keyboard.press("Home");
    await expect(tab(page, /^Active/)).toBeFocused();

    await page.getByRole("button", { name: "Archive Seasonal" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeHidden();
    expect(fake.writes).toHaveLength(0);
  });
});

test.describe("Admin categories on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("tabs and actions fit without sideways scroll", async ({ page }) => {
    await install(page);
    await page.goto("/admin/categories");
    await expect(tab(page, /^Archived/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Archive Toys" })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
