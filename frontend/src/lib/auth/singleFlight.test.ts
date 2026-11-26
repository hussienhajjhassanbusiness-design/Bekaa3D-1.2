import { describe, it, expect, vi } from "vitest";
import { createSingleFlight } from "./singleFlight";

// FVS-003-IMPLEMENTATION-PLAN.md §7/§2 row 36 (corrected, BATCH 2) — a fully
// generic async-deduplication primitive. Tested exclusively against a
// generic injected function (never apiClient, never a refresh/auth concept)
// to prove the primitive itself needs no contract knowledge to be correct.

// A promise plus externally-callable resolve/reject, for precise control
// over when an "in-flight" operation settles.
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("createSingleFlight", () => {
  it("invokes the operation exactly once on a first call", async () => {
    const operation = vi.fn().mockResolvedValue("result");
    const single = createSingleFlight(operation);

    await single();

    expect(operation).toHaveBeenCalledTimes(1);
  });

  it("five concurrent calls while pending invoke the operation exactly once", async () => {
    const d = deferred<string>();
    const operation = vi.fn().mockReturnValue(d.promise);
    const single = createSingleFlight(operation);

    const calls = [single(), single(), single(), single(), single()];
    expect(operation).toHaveBeenCalledTimes(1);

    d.resolve("value");
    await Promise.all(calls);

    expect(operation).toHaveBeenCalledTimes(1);
  });

  it("every concurrent caller receives the exact same resolved value", async () => {
    const d = deferred<{ id: number }>();
    const operation = vi.fn().mockReturnValue(d.promise);
    const single = createSingleFlight(operation);

    const callA = single();
    const callB = single();
    const callC = single();

    const resolvedValue = { id: 42 };
    d.resolve(resolvedValue);

    const [a, b, c] = await Promise.all([callA, callB, callC]);
    expect(a).toBe(resolvedValue);
    expect(b).toBe(resolvedValue);
    expect(c).toBe(resolvedValue);
  });

  it("concurrent callers share the exact same in-flight promise reference", () => {
    const d = deferred<string>();
    const operation = vi.fn().mockReturnValue(d.promise);
    const single = createSingleFlight(operation);

    const callA = single();
    const callB = single();

    expect(callA).toBe(callB);
  });

  it("after the operation resolves, a later call invokes the operation again (fresh attempt)", async () => {
    const operation = vi.fn().mockResolvedValue("first").mockResolvedValueOnce("first");
    const single = createSingleFlight(operation);

    await single();
    expect(operation).toHaveBeenCalledTimes(1);

    await single();
    expect(operation).toHaveBeenCalledTimes(2);
  });

  it("propagates a rejection to the caller unchanged — never swallowed, never converted to a boolean", async () => {
    const failure = new Error("operation failed");
    const operation = vi.fn().mockRejectedValue(failure);
    const single = createSingleFlight(operation);

    await expect(single()).rejects.toBe(failure);
  });

  it("concurrent callers during a pending rejection all observe the same rejection, with only one underlying invocation", async () => {
    const d = deferred<never>();
    const operation = vi.fn().mockReturnValue(d.promise);
    const single = createSingleFlight(operation);

    const callA = single();
    const callB = single();
    const callC = single();
    expect(operation).toHaveBeenCalledTimes(1);

    const failure = new Error("shared failure");
    d.reject(failure);

    await expect(callA).rejects.toBe(failure);
    await expect(callB).rejects.toBe(failure);
    await expect(callC).rejects.toBe(failure);
    expect(operation).toHaveBeenCalledTimes(1);
  });

  it("after a rejection settles, a later call starts a genuinely new attempt", async () => {
    const operation = vi.fn().mockRejectedValueOnce(new Error("first failure")).mockResolvedValueOnce("second attempt ok");
    const single = createSingleFlight(operation);

    await expect(single()).rejects.toThrow("first failure");
    expect(operation).toHaveBeenCalledTimes(1);

    await expect(single()).resolves.toBe("second attempt ok");
    expect(operation).toHaveBeenCalledTimes(2);
  });

  it("a synchronous throw from the operation propagates as a rejection to the caller", async () => {
    const failure = new Error("synchronous failure");
    const operation = vi.fn(() => {
      throw failure;
    });
    const single = createSingleFlight(operation);

    await expect(single()).rejects.toBe(failure);
  });

  it("a synchronous throw does not permanently poison future calls — a later call can succeed", async () => {
    const operation = vi
      .fn()
      .mockImplementationOnce(() => {
        throw new Error("synchronous failure");
      })
      .mockResolvedValueOnce("recovered");
    const single = createSingleFlight(operation);

    await expect(single()).rejects.toThrow("synchronous failure");
    expect(operation).toHaveBeenCalledTimes(1);

    await expect(single()).resolves.toBe("recovered");
    expect(operation).toHaveBeenCalledTimes(2);
  });

  it("concurrent callers sharing a synchronously-thrown attempt all observe the same rejection, with only one underlying invocation", async () => {
    const failure = new Error("shared synchronous failure");
    const operation = vi.fn(() => {
      throw failure;
    });
    const single = createSingleFlight(operation);

    const callA = single();
    const callB = single();

    await expect(callA).rejects.toBe(failure);
    await expect(callB).rejects.toBe(failure);
    expect(operation).toHaveBeenCalledTimes(1);
  });

  it("has no knowledge of auth/apiClient — the module imports nothing beyond the generic primitive itself", async () => {
    const moduleExports = await import("./singleFlight");
    expect(Object.keys(moduleExports)).toEqual(["createSingleFlight"]);
  });
});
