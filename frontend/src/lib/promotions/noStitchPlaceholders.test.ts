import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, it, expect } from "vitest";

// The Stitch home mock-up's promotion is design-only placeholder copy. The
// shipped app must render only the backend's real promotions, so none of
// that copy may appear in production source (tests are excluded: they may
// assert its absence).
const PLACEHOLDERS = [/Storewide Launch/i, /30% OFF/i, /REDEEM DISCOUNT/i, /lh3\.googleusercontent\.com/i];

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(tsx?|css)$/.test(entry) && !/\.test\.tsx?$/.test(entry) ? [path] : [];
  });
}

describe("no Stitch placeholder campaign in production code", () => {
  it("ships none of the mock-up's promotion copy or hosted images", () => {
    const offenders = sourceFiles(join(process.cwd(), "src")).filter((file) => {
      const text = readFileSync(file, "utf8");
      return PLACEHOLDERS.some((pattern) => pattern.test(text));
    });
    expect(offenders).toEqual([]);
  });
});
