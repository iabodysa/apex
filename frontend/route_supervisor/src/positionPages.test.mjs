// Copyright (c) 2026, afmcoltd
import { describe, expect, it } from "vitest";

import { mergePositionPages, nextPositionStart } from "./positionPages.js";

describe("fleet position pages", () => {
  it("advances by the scoped plan window even when some plans have no trip", () => {
    expect(nextPositionStart({ start: 0, page_length: 50, returned: 12 })).toBe(50);
  });

  it("keeps page order and replaces a position repeated across a moving boundary", () => {
    const pages = [
      {
        start: 0,
        positions: [
          { dispatch_trip: "DT-1", updated_at: "old" },
          { dispatch_trip: "DT-2" },
        ],
      },
      {
        start: 50,
        positions: [
          { dispatch_trip: "DT-1", updated_at: "new" },
          { dispatch_trip: "DT-3" },
        ],
      },
    ];

    expect(mergePositionPages(pages)).toEqual([
      { dispatch_trip: "DT-1", updated_at: "new" },
      { dispatch_trip: "DT-2" },
      { dispatch_trip: "DT-3" },
    ]);
  });
});
