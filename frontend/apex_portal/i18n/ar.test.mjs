import { describe, expect, it } from "vitest";
import { ar } from "./ar.js";

describe("Arabic foundation copy", () => {
  it("provides concise Saudi business Arabic for shared shell states", () => {
    expect(ar.skipToContent).toBe("تجاوز إلى المحتوى");
    expect(ar.primaryNavigation).toBe("التنقل الرئيسي");
    expect(ar.accessDeniedTitle).toBe("لا تملك صلاحية الوصول");
    expect(Object.isFrozen(ar)).toBe(true);
  });
});
