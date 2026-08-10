import { expect, it } from "vitest";
import { boundedPreloadWindow } from "./preload.js";

it("preloads only a bounded, forward-looking media window", () => {
  const candidates = [5n, 1n, 4n, 3n, 2n].map((timestampNs) => ({
    timestampNs,
    src: String(timestampNs)
  }));
  expect(boundedPreloadWindow(candidates, 2n, 2).map(({ src }) => src)).toEqual(
    ["2", "3"]
  );
});
