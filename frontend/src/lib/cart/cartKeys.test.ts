import { describe, it, expect } from "vitest";
import { cartKeys } from "./cartKeys";

// #ARCHITECTURE-CANONICAL-CART-QUERY — one cart per user. The current
// cart key carries the signed-in user's id so a user switch can never
// read the previous user's cached cart, and `root` is what every write
// invalidates and what logout removes.

describe("cartKeys", () => {
  it("has a stable root key", () => {
    expect(cartKeys.root).toEqual(["cart"]);
  });

  it("derives the current key from the root plus the user id", () => {
    expect(cartKeys.current("u-1")).toEqual(["cart", "current", "u-1"]);
  });

  it("gives two users different keys", () => {
    expect(cartKeys.current("u-1")).not.toEqual(cartKeys.current("u-2"));
  });
});
