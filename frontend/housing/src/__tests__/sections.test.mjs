// Copyright (c) 2026, afmcoltd
import { describe, expect, it } from "vitest";

import {
  chooseLanding,
  domainForSection,
  sectionsForDomain,
  visibleDomains,
} from "../sections.js";

describe("housing portal information architecture", () => {
  it("groups every operational route under one stable domain", () => {
    expect(domainForSection("beds")).toBe("residents");
    expect(domainForSection("arrivals")).toBe("residents");
    expect(domainForSection("transfer")).toBe("residents");
    expect(domainForSection("custody")).toBe("custody");
    expect(domainForSection("count")).toBe("count");
    expect(domainForSection("delivery")).toBe("delivery");
    expect(domainForSection("safety")).toBe("safety");
  });

  it("keeps domain navigation permission-derived", () => {
    const granted = new Set(["arrivals", "count"]);
    expect(visibleDomains(granted).map((domain) => domain.id)).toEqual([
      "today",
      "residents",
      "count",
    ]);
    expect(sectionsForDomain("residents", granted).map((section) => section.id)).toEqual([
      "arrivals",
    ]);
    expect(sectionsForDomain("count", granted).map((section) => section.id)).toEqual(["count"]);
    expect(sectionsForDomain("delivery", granted).map((section) => section.id)).toEqual([]);
  });

  it("lands safety entry on safety and housing entry on the overview when useful", () => {
    expect(chooseLanding("safety", new Set(["safety", "beds"]))).toBe("/safety");
    expect(chooseLanding("housing", new Set(["beds"]))).toBe("/today");
    expect(chooseLanding("housing", new Set(["delivery"]))).toBe("/delivery");
    expect(chooseLanding("housing", new Set())).toBe("/no-access");
  });
});
