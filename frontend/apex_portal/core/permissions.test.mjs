import { describe, expect, it } from "vitest";
import { can, normalizeCapabilities } from "./permissions.js";

describe("capabilities", () => {
  it("grants only an exact server-provided capability", () => {
    const granted = normalizeCapabilities(["worker.trip.read"]);
    expect(can("worker.trip.read", granted)).toBe(true);
    expect(can("worker.trip.write", granted)).toBe(false);
    expect(can("worker", granted)).toBe(false);
  });

  it("deduplicates, sorts, and freezes capability values", () => {
    const granted = normalizeCapabilities(["z.read", "a.read", "z.read"]);
    expect(granted).toEqual(["a.read", "z.read"]);
    expect(Object.isFrozen(granted)).toBe(true);
  });

  it("rejects malformed capability values instead of granting around them", () => {
    expect(() => normalizeCapabilities(["worker.home", ""])).toThrow(/capability/);
    expect(() => normalizeCapabilities(["worker.home", null])).toThrow(/capability/);
  });
});
