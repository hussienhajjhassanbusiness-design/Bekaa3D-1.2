import { describe, it, expect, vi, afterEach } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { useQueryClient } from "@tanstack/react-query";
import { useToast } from "@/components/feedback/ToastProvider";
import RootLayout from "./layout";

// FVS001-T14 — the one composition-level integration test: proves the REAL
// provider/shell nesting (QueryProvider -> ToastProvider -> AppLayout ->
// dev-only banner -> children), not a duplicate of any individual
// component's own test (those already exist for AppLayout/Header/Footer/
// SkipLink/QueryProvider/ToastProvider/BackendUnreachableBanner).
//
// RootLayout returns real <html>/<body> tags. Rendering it through
// @testing-library/react's render() would nest a second <html>/<body> inside
// jsdom's own live document — invalid, misleading DOM that would produce
// undefined parsing behavior, not a meaningful test. Instead this renders
// the real component tree to an HTML string via react-dom/server (an
// honest, supported SSR entry point that Client Components render through
// correctly on their initial pass) and parses that string as its own
// standalone Document via DOMParser.
//
// That Document has no associated `window` (DOMParser output is detached),
// so @testing-library/dom's getByRole/getAllByRole cannot be used here —
// they unconditionally call `window.getComputedStyle` while computing
// accessibility (to filter out display:none/visibility:hidden elements),
// which throws "Cannot read properties of null" against a windowless
// document, even when matching elements genuinely exist (confirmed by
// running this file: it wasn't only a zero-results/error-formatting
// artifact). Landmark checks below therefore use plain tag/attribute
// selectors instead: a bare <header>/<main>/<footer> that isn't nested
// inside another sectioning element (article/aside/nav/section) has an
// unambiguous implicit ARIA role of banner/main/contentinfo per the
// HTML-AAM spec — true of this exact composition (AppLayout renders them as
// direct children of <body>) — so counting the tags themselves is an
// honest, accurate proxy for the landmark roles in this specific structure.
vi.mock("@/components/feedback/BackendUnreachableBanner", () => ({
  BackendUnreachableBanner: () => <div data-testid="dev-banner-marker" />,
}));

function renderLayoutDocument(children: React.ReactNode): Document {
  // The root "/" segment has no dynamic params — LayoutProps<"/">'s params
  // resolves to an empty object, matching Next.js's own generated type.
  const html = renderToStaticMarkup(<RootLayout params={Promise.resolve({})}>{children}</RootLayout>);
  return new DOMParser().parseFromString(html, "text/html");
}

function ContextProbe() {
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const ok = typeof showToast === "function" && queryClient != null;
  return <div data-testid="context-probe">{ok ? "context-ok" : "context-missing"}</div>;
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("RootLayout composition (FVS001-T14)", () => {
  it("composes exactly one banner, one main, and one contentinfo landmark around the supplied route content", () => {
    const doc = renderLayoutDocument(<p data-testid="route-content">Route content</p>);

    // See the top-of-file note: plain tag counts, not getByRole, against
    // this windowless parsed document — <header>/<main>/<footer> as direct
    // children of <body> have unambiguous implicit banner/main/contentinfo
    // roles here.
    expect(doc.querySelectorAll("body > header")).toHaveLength(1);
    expect(doc.querySelectorAll("main")).toHaveLength(1);
    expect(doc.querySelectorAll("body > footer")).toHaveLength(1);
  });

  it("renders SkipLink, Header, the supplied route child, and Footer inside the composed shell", () => {
    const doc = renderLayoutDocument(<p data-testid="route-content">Route content</p>);

    expect(doc.body.textContent).toContain("Skip to main content");
    expect(doc.querySelector("header")?.textContent).toContain("Bekaa3D");
    expect(doc.querySelector('[data-testid="route-content"]')).not.toBeNull();
    expect(doc.querySelector("footer")?.textContent).toContain("Bekaa3D");
  });

  it('places the supplied route content inside the single <main id="main-content"> landmark, not a second one', () => {
    const doc = renderLayoutDocument(<p data-testid="route-content">Route content</p>);

    const main = doc.querySelector("#main-content");
    expect(main).not.toBeNull();
    expect(doc.querySelectorAll("main")).toHaveLength(1);
    expect(main?.querySelector('[data-testid="route-content"]')).not.toBeNull();
  });

  it("provides working QueryProvider/ToastProvider context to descendants (a real context probe, not just absence of a crash)", () => {
    const doc = renderLayoutDocument(<ContextProbe />);

    expect(doc.querySelector('[data-testid="context-probe"]')?.textContent).toBe("context-ok");
  });

  it("does not mount BackendUnreachableBanner outside development (default test NODE_ENV)", () => {
    const doc = renderLayoutDocument(<p>Route content</p>);

    expect(doc.querySelector('[data-testid="dev-banner-marker"]')).toBeNull();
  });

  it("mounts BackendUnreachableBanner only when NODE_ENV is development", () => {
    vi.stubEnv("NODE_ENV", "development");

    const doc = renderLayoutDocument(<p>Route content</p>);

    expect(doc.querySelector('[data-testid="dev-banner-marker"]')).not.toBeNull();
  });
});
