import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act, waitFor } from "@testing-library/react";
import { createRef } from "react";
import { CaptchaWidget, type CaptchaWidgetHandle } from "./CaptchaWidget";
import { __resetTurnstileLoaderForTests } from "@/lib/captcha/turnstileLoader";

interface RenderOptions {
  sitekey: string;
  callback: (token: string) => void;
  "expired-callback": () => void;
  "error-callback": () => void;
}

function installFakeTurnstile() {
  let options: RenderOptions | undefined;
  const api = {
    render: vi.fn((_el: HTMLElement, opts: RenderOptions) => {
      options = opts;
      return "widget-1";
    }),
    reset: vi.fn(),
    remove: vi.fn(),
  };
  (window as unknown as { turnstile?: unknown }).turnstile = api;
  return { api, options: () => options! };
}

beforeEach(() => {
  __resetTurnstileLoaderForTests();
});

afterEach(() => {
  delete (window as unknown as { turnstile?: unknown }).turnstile;
  document.querySelectorAll("script[data-turnstile-loader]").forEach((node) => node.remove());
});

describe("CaptchaWidget", () => {
  it("renders the Turnstile widget with the given site key and forwards the issued token", async () => {
    const fake = installFakeTurnstile();
    const onToken = vi.fn();
    render(<CaptchaWidget siteKey="1x00000000000000000000AA" onToken={onToken} />);

    await waitFor(() => expect(fake.api.render).toHaveBeenCalledTimes(1));
    expect(fake.options().sitekey).toBe("1x00000000000000000000AA");

    act(() => fake.options().callback("XXXX.DUMMY.TOKEN.XXXX"));
    expect(onToken).toHaveBeenLastCalledWith("XXXX.DUMMY.TOKEN.XXXX");
  });

  it("clears the token when it expires", async () => {
    const fake = installFakeTurnstile();
    const onToken = vi.fn();
    render(<CaptchaWidget siteKey="k" onToken={onToken} />);
    await waitFor(() => expect(fake.api.render).toHaveBeenCalled());

    act(() => fake.options().callback("t1"));
    act(() => fake.options()["expired-callback"]());
    expect(onToken).toHaveBeenLastCalledWith(null);
  });

  it("clears the token and shows safe copy when the widget errors", async () => {
    const fake = installFakeTurnstile();
    const onToken = vi.fn();
    render(<CaptchaWidget siteKey="k" onToken={onToken} />);
    await waitFor(() => expect(fake.api.render).toHaveBeenCalled());

    act(() => fake.options()["error-callback"]());
    expect(onToken).toHaveBeenLastCalledWith(null);
    expect(screen.getByRole("alert")).toHaveTextContent(/verification couldn.t load/i);
  });

  it("reset() resets the widget and clears the token (tokens are single-use)", async () => {
    const fake = installFakeTurnstile();
    const onToken = vi.fn();
    const ref = createRef<CaptchaWidgetHandle>();
    render(<CaptchaWidget ref={ref} siteKey="k" onToken={onToken} />);
    await waitFor(() => expect(fake.api.render).toHaveBeenCalled());

    act(() => fake.options().callback("t1"));
    act(() => ref.current!.reset());
    expect(fake.api.reset).toHaveBeenCalledWith("widget-1");
    expect(onToken).toHaveBeenLastCalledWith(null);
  });

  it("removes the widget on unmount", async () => {
    const fake = installFakeTurnstile();
    const { unmount } = render(<CaptchaWidget siteKey="k" onToken={vi.fn()} />);
    await waitFor(() => expect(fake.api.render).toHaveBeenCalled());
    unmount();
    expect(fake.api.remove).toHaveBeenCalledWith("widget-1");
  });

  it("injects the explicit-render Turnstile script once when the API is not present yet", async () => {
    render(<CaptchaWidget siteKey="k" onToken={vi.fn()} />);
    render(<CaptchaWidget siteKey="k" onToken={vi.fn()} />);
    const scripts = document.querySelectorAll("script[data-turnstile-loader]");
    expect(scripts).toHaveLength(1);
    expect((scripts[0] as HTMLScriptElement).src).toBe(
      "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit"
    );
  });

  it("shows safe copy when the script fails to load", async () => {
    const onToken = vi.fn();
    render(<CaptchaWidget siteKey="k" onToken={onToken} />);
    const script = document.querySelector("script[data-turnstile-loader]")!;
    act(() => {
      script.dispatchEvent(new Event("error"));
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(/verification couldn.t load/i);
    expect(onToken).not.toHaveBeenCalledWith(expect.any(String));
  });

  it("shows safe copy and renders nothing when no site key is configured", () => {
    render(<CaptchaWidget siteKey={null} onToken={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/verification is unavailable/i);
    expect(document.querySelector("script[data-turnstile-loader]")).toBeNull();
  });
});
