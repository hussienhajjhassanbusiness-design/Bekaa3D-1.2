"use client"; // Error boundaries must be Client Components

// Redesign Batch 11 (landmarks): the same category-A render-error fallback
// as the root error.tsx, but at the admin segment, so it renders INSIDE
// AdminShell (src/app/admin/layout.tsx). The root boundary replaces the
// admin layout, and the storefront chrome is suppressed on /admin for an
// administrator, so the fallback there had no <main> landmark and no
// skip-link target. Behaviour (retry, no raw error shown) is identical.
export { default } from "../error";
