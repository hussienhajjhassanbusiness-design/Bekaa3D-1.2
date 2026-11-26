// FVS-003-IMPLEMENTATION-PLAN.md §10/§17 (corrected, BATCH 2) — a fully
// generic, opaque, same-browser cross-tab signaling primitive. It has NO
// knowledge of logout's HTTP semantics, AuthProvider, cookies, CSRF, or user
// identity — only that "something happened" (an opaque string tag) can be
// announced and observed. Wiring this into useLogout's success handler is
// T09's job, once T09 itself unblocks; this module is never imported by
// anything auth-specific here.
//
// No module-level BroadcastChannel is ever constructed — only
// `createCrossTabSignal()` touches the browser API, and only when actually
// called, so importing this module stays safe during SSR/build/Node test
// execution. If BroadcastChannel is unsupported in the current environment,
// every operation becomes a safe no-op (per the plan's explicit "no
// localStorage fallback" decision, §17) rather than silently inventing a
// different persistence-based mechanism.

const CHANNEL_NAME = "bekaa3d-auth";

export type CrossTabSignalListener = (eventType: string) => void;

export interface CrossTabSignal {
  announce(eventType: string): void;
  subscribe(listener: CrossTabSignalListener): () => void;
  close(): void;
}

interface SignalMessage {
  type: string;
}

function isSignalMessage(data: unknown): data is SignalMessage {
  return typeof data === "object" && data !== null && typeof (data as { type?: unknown }).type === "string";
}

const NOOP_SIGNAL: CrossTabSignal = {
  announce() {},
  subscribe() {
    return () => {};
  },
  close() {},
};

export function createCrossTabSignal(): CrossTabSignal {
  if (typeof BroadcastChannel === "undefined") {
    return NOOP_SIGNAL;
  }

  const channel = new BroadcastChannel(CHANNEL_NAME);
  const listeners = new Set<CrossTabSignalListener>();

  function handleMessage(event: MessageEvent) {
    if (!isSignalMessage(event.data)) {
      return;
    }
    for (const listener of listeners) {
      listener(event.data.type);
    }
  }

  channel.addEventListener("message", handleMessage);

  return {
    announce(eventType: string) {
      const message: SignalMessage = { type: eventType };
      channel.postMessage(message);
    },
    subscribe(listener: CrossTabSignalListener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    close() {
      channel.removeEventListener("message", handleMessage);
      channel.close();
      listeners.clear();
    },
  };
}
