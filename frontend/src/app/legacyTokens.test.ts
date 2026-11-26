import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

// Redesign Batch 11: the pre-Stitch compatibility aliases were deleted from
// globals.css. Tailwind generates nothing for an unknown utility, so a
// reintroduced alias class would silently render unstyled text instead of
// failing the build. This guard keeps them out of the source.
const SRC = join(process.cwd(), "src");

const LEGACY_CLASSES = [
  "brand-dark-green",
  "brand-green",
  "brand-lime",
  "text-text-primary",
  "text-text-secondary",
  "text-text-disabled",
  "text-text-on-brand",
  "text-text-link",
  "surface-base",
  "surface-subtle",
  "surface-sunken",
  "border-border-default",
  "border-border-strong",
  "border-border-focus",
  "success-bg",
  "warning-bg",
  "warning-text",
  "danger-bg",
  "info-bg",
  "text-danger",
  "bg-danger",
  "border-danger",
  "text-success",
  "text-h1",
  "text-h2",
  "text-h3",
  "text-h4",
  "text-body",
  "text-caption",
  "text-label",
  "tracking-label",
  "rounded-md",
  "rounded-pill",
  "shadow-elevation-1",
  "shadow-elevation-2",
  "shadow-elevation-3",
];
// neutral-50 … neutral-900 with any utility prefix (bg-, text-, border-…).
const NEUTRAL = /(?<=[\s"'`:-])neutral-\d{2,3}(?=[\s"'`/]|$)/;

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    if (!/\.(tsx?|css)$/.test(entry.name) || /\.test\.tsx?$/.test(entry.name)) return [];
    return [path];
  });
}

describe("legacy design-token aliases (removed in Batch 11)", () => {
  it("are not used as classes anywhere in src", () => {
    const pattern = new RegExp(
      `(?<=[\\s"'\`:])(?:${LEGACY_CLASSES.map((c) => c.replace(/-/g, "\\-")).join("|")})(?=[\\s"'\`/]|$)`
    );
    const offenders = sourceFiles(SRC).flatMap((file) =>
      readFileSync(file, "utf8")
        .split(/\r?\n/)
        .map((line, index) => ({ line, index }))
        .filter(({ line }) => pattern.test(line) || NEUTRAL.test(line))
        .map(({ line, index }) => `${file}:${index + 1}: ${line.trim()}`)
    );
    expect(offenders).toEqual([]);
  });

  it("are no longer defined in globals.css", () => {
    const css = readFileSync(join(SRC, "app", "globals.css"), "utf8");
    expect(css).not.toMatch(/--color-(brand-|ink|success|danger|neutral-|text-|surface-base|border-default)/);
    expect(css).not.toMatch(/--text-(h[1-4]|body|caption|label):/);
    expect(css).not.toMatch(/--shadow-elevation|--radius-(sm|md|pill)|--tracking-label/);
  });
});
