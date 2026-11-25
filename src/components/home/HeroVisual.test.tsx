import { describe, it, expect, vi, afterEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/apiClient";

import { HeroSection } from "./HeroSection";

const HERO_URL = "/media/home/hero/0123456789abcdef0123456789abcdef.webp";
const LOGO = 'img[src="/brand/bekaa3d-mark.png"]';

function mockHero(result: { url: string | null } | Error | "never") {
  return vi.spyOn(apiClient, "get").mockImplementation(async (path: unknown) => {
    expect(path).toBe("/api/v1/home/hero-image");
    if (result === "never") return new Promise(() => {});
    if (result instanceof Error) throw result;
    return result;
  });
}

function renderHero() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <HeroSection />
    </QueryClientProvider>
  );
}

function visual(container: HTMLElement) {
  return container.querySelector<HTMLElement>("[data-hero-visual]")!;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("HeroVisual (homepage hero image)", () => {
  it("falls back to the existing brand visual when no hero image is set", async () => {
    mockHero({ url: null });
    const { container } = renderHero();

    await waitFor(() => expect(visual(container)).toHaveAttribute("data-hero-visual", "default"));
    expect(container.querySelector(LOGO)).not.toBeNull();
    expect(container.querySelector(`img[src="${HERO_URL}"]`)).toBeNull();
  });

  it("renders the saved hero image, covering the fixed square panel", async () => {
    mockHero({ url: HERO_URL });
    const { container } = renderHero();

    await waitFor(() => expect(visual(container)).toHaveAttribute("data-hero-visual", "custom"));
    const image = container.querySelector(`img[src="${HERO_URL}"]`);
    expect(image).toHaveClass("absolute", "inset-0", "h-full", "w-full", "object-cover");
    expect(visual(container)).toHaveClass("aspect-square", "overflow-hidden");
    expect(container.querySelector(LOGO)).toBeNull();
  });

  it("shows the empty panel while loading, so the default never flashes before a saved image", () => {
    mockHero("never");
    const { container } = renderHero();

    expect(visual(container)).toHaveAttribute("data-hero-visual", "loading");
    expect(container.querySelectorAll("[data-hero-visual] img")).toHaveLength(0);
    expect(visual(container)).toHaveClass("aspect-square");
  });

  it("falls back to the brand visual when the backend can't be reached", async () => {
    mockHero(Object.assign(new Error("offline"), { kind: "network" }));
    const { container } = renderHero();

    await waitFor(() => expect(visual(container)).toHaveAttribute("data-hero-visual", "default"));
    expect(container.querySelector(LOGO)).not.toBeNull();
  });

  it("falls back to the brand visual when the saved image fails to load — never a broken image", async () => {
    mockHero({ url: HERO_URL });
    const { container } = renderHero();

    await waitFor(() => expect(container.querySelector(`img[src="${HERO_URL}"]`)).not.toBeNull());
    fireEvent.error(container.querySelector(`img[src="${HERO_URL}"]`)!);

    await waitFor(() => expect(visual(container)).toHaveAttribute("data-hero-visual", "default"));
    expect(container.querySelector(`img[src="${HERO_URL}"]`)).toBeNull();
    expect(container.querySelector(LOGO)).not.toBeNull();
  });

  it("keeps the hero layout: decorative, the floating cards stay, hidden on phones and shown from tablet up", async () => {
    mockHero({ url: HERO_URL });
    const { container } = renderHero();

    await waitFor(() => expect(visual(container)).toHaveAttribute("data-hero-visual", "custom"));
    const side = visual(container).parentElement!;
    expect(side).toHaveAttribute("aria-hidden", "true");
    expect(side).toHaveClass("hidden", "tablet:block");
    expect(container.querySelector(`img[src="${HERO_URL}"]`)).toHaveAttribute("alt", "");
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(side).toHaveTextContent("Physical prints");
    expect(side).toHaveTextContent("STL files");
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
  });
});
