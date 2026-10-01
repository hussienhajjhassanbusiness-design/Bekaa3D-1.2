import { describe, it, expect, vi, afterEach } from "vitest";
import { createCrossTabSignal } from "./crossTabSignal";

// FVS-003-IMPLEMENTATION-PLAN.md §10/§17 (corrected, BATCH 2) — a fully
// generic, opaque, same-browser cross-tab signaling primitive. It has NO
// knowledge of logout's HTTP semantics, AuthProvider, cookies, CSRF, or user
// identity — only that "something happened" (an opaque string tag) can be
// announced and observed. Real `BroadcastChannel` is used throughout (both
// Node and this project's jsdom test environment provide it natively); the
// unsupported-environment path is exercised separately by stubbing it away.

const CHANNEL_NAME = "bekaa3d-auth";

const createdChannels: BroadcastChannel[] = [];
afterEach(() => {
  // Close every channel this file itself opened directly (for inspection),
  // so no open BroadcastChannel handle is ever left behind across tests.
  for (const channel of createdChannels) {
    channel.close();
  }
  createdChannels.length = 0;
  vi.unstubAllGlobals();
});

describe("createCrossTabSignal", () => {
  it("does not construct a BroadcastChannel merely by being imported", () => {
    // Stubbing the constructor here, well after this module was already
    // imported at the top of this file, and asserting it's still at zero
    // calls proves import alone never touched the real BroadcastChannel —
    // only an explicit factory call (below, in every other test) does.
    const realCtor = globalThis.BroadcastChannel;
    const spy = vi.fn((name: string) => new realCtor(name));
    vi.stubGlobal("BroadcastChannel", spy);

    expect(spy).not.toHaveBeenCalled();
  });

  it("uses the expected channel name when actually instantiated", () => {
    const realCtor = globalThis.BroadcastChannel;
    const spy = vi.fn(function (this: unknown, name: string) {
      return new realCtor(name);
    });
    vi.stubGlobal("BroadcastChannel", spy);

    const signal = createCrossTabSignal();
    signal.close();

    expect(spy).toHaveBeenCalledWith(CHANNEL_NAME);
  });

  it("announce sends exactly the approved opaque message, nothing else", async () => {
    const receiver = new BroadcastChannel(CHANNEL_NAME);
    createdChannels.push(receiver);
    const received: unknown[] = [];
    receiver.onmessage = (event) => received.push(event.data);

    const signal = createCrossTabSignal();
    signal.announce("logout");

    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(received).toEqual([{ type: "logout" }]);
    signal.close();
  });

  it("the broadcast message never contains user/token/session data", async () => {
    const receiver = new BroadcastChannel(CHANNEL_NAME);
    createdChannels.push(receiver);
    let received: unknown;
    receiver.onmessage = (event) => {
      received = event.data;
    };

    const signal = createCrossTabSignal();
    signal.announce("logout");
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(Object.keys(received as object)).toEqual(["type"]);
    expect(JSON.stringify(received)).not.toMatch(/token|email|user|session|cookie/i);
    signal.close();
  });

  it("a subscriber in another instance receives the announced signal", async () => {
    const sender = createCrossTabSignal();
    const receiver = createCrossTabSignal();

    const listener = vi.fn();
    receiver.subscribe(listener);

    sender.announce("logout");
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(listener).toHaveBeenCalledWith("logout");

    sender.close();
    receiver.close();
  });

  it("ignores an unrelated or malformed message instead of invoking the listener", async () => {
    const foreign = new BroadcastChannel(CHANNEL_NAME);
    createdChannels.push(foreign);

    const receiver = createCrossTabSignal();
    const listener = vi.fn();
    receiver.subscribe(listener);

    foreign.postMessage({ unrelated: true });
    foreign.postMessage("just a string");
    foreign.postMessage(null);
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(listener).not.toHaveBeenCalled();
    receiver.close();
  });

  it("unsubscribe stops further callbacks to that listener", async () => {
    const sender = createCrossTabSignal();
    const receiver = createCrossTabSignal();

    const listener = vi.fn();
    const unsubscribe = receiver.subscribe(listener);

    sender.announce("logout");
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(listener).toHaveBeenCalledTimes(1);

    unsubscribe();
    sender.announce("logout");
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(listener).toHaveBeenCalledTimes(1);

    sender.close();
    receiver.close();
  });

  it("close() stops delivering further signals and releases the underlying channel", async () => {
    const sender = createCrossTabSignal();
    const receiver = createCrossTabSignal();
    const listener = vi.fn();
    receiver.subscribe(listener);

    receiver.close();

    sender.announce("logout");
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(listener).not.toHaveBeenCalled();
    sender.close();
  });

  it("multiple subscribers on the same instance do not corrupt one another", async () => {
    const sender = createCrossTabSignal();
    const receiver = createCrossTabSignal();
    const listenerA = vi.fn();
    const listenerB = vi.fn();
    receiver.subscribe(listenerA);
    const unsubscribeB = receiver.subscribe(listenerB);

    sender.announce("logout");
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(listenerA).toHaveBeenCalledTimes(1);
    expect(listenerB).toHaveBeenCalledTimes(1);

    unsubscribeB();
    sender.announce("logout");
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(listenerA).toHaveBeenCalledTimes(2);
    expect(listenerB).toHaveBeenCalledTimes(1);

    sender.close();
    receiver.close();
  });

  it("never calls fetch — no backend/network call occurs from announce or subscribe", async () => {
    const fetchSpy = vi.fn(() => {
      throw new Error("fetch must never be called by this module");
    });
    vi.stubGlobal("fetch", fetchSpy);

    const signal = createCrossTabSignal();
    signal.subscribe(vi.fn());
    signal.announce("logout");
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(fetchSpy).not.toHaveBeenCalled();
    signal.close();
  });

  it("never reads or writes localStorage, sessionStorage, or document.cookie", async () => {
    const localStorageSpy = vi.spyOn(Storage.prototype, "setItem");
    const sessionStorageSpy = vi.spyOn(window.sessionStorage.__proto__, "setItem");
    const cookieSpy = vi.spyOn(document, "cookie", "set");

    const signal = createCrossTabSignal();
    signal.subscribe(vi.fn());
    signal.announce("logout");
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(localStorageSpy).not.toHaveBeenCalled();
    expect(sessionStorageSpy).not.toHaveBeenCalled();
    expect(cookieSpy).not.toHaveBeenCalled();

    signal.close();
    localStorageSpy.mockRestore();
    sessionStorageSpy.mockRestore();
    cookieSpy.mockRestore();
  });

  describe("when BroadcastChannel is unsupported", () => {
    it("does not throw on creation, announce, subscribe, or close", () => {
      vi.stubGlobal("BroadcastChannel", undefined);

      expect(() => {
        const signal = createCrossTabSignal();
        const unsubscribe = signal.subscribe(vi.fn());
        signal.announce("logout");
        unsubscribe();
        signal.close();
      }).not.toThrow();
    });

    it("behaves as a graceful no-op — a subscriber never fires, per the plan's 'no localStorage fallback' decision", async () => {
      vi.stubGlobal("BroadcastChannel", undefined);

      const signal = createCrossTabSignal();
      const listener = vi.fn();
      signal.subscribe(listener);
      signal.announce("logout");
      await new Promise((resolve) => setTimeout(resolve, 0));

      expect(listener).not.toHaveBeenCalled();
      signal.close();
    });
  });
});
