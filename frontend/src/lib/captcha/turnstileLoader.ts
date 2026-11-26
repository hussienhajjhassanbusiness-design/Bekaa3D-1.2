// Loads Cloudflare Turnstile's script once, in explicit-render mode, and
// resolves with its global API. Only the members this app uses are typed.
export const TURNSTILE_SCRIPT_URL = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

export interface TurnstileRenderOptions {
  sitekey: string;
  callback: (token: string) => void;
  "expired-callback": () => void;
  "error-callback": () => void;
}

export interface TurnstileApi {
  render: (container: HTMLElement, options: TurnstileRenderOptions) => string | undefined;
  reset: (widgetId: string) => void;
  remove: (widgetId: string) => void;
}

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

let pending: Promise<TurnstileApi> | null = null;

export function loadTurnstile(): Promise<TurnstileApi> {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("Turnstile requires a browser"));
  }
  if (window.turnstile) {
    return Promise.resolve(window.turnstile);
  }
  if (pending) {
    return pending;
  }
  pending = new Promise<TurnstileApi>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = TURNSTILE_SCRIPT_URL;
    script.async = true;
    script.defer = true;
    script.dataset.turnstileLoader = "";
    script.addEventListener("load", () => {
      if (window.turnstile) {
        resolve(window.turnstile);
      } else {
        pending = null;
        reject(new Error("Turnstile API missing after load"));
      }
    });
    script.addEventListener("error", () => {
      // Allow a later mount to retry.
      pending = null;
      script.remove();
      reject(new Error("Turnstile script failed to load"));
    });
    document.head.appendChild(script);
  });
  return pending;
}

export function __resetTurnstileLoaderForTests() {
  pending = null;
}
