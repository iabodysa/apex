// Copyright (c) 2026, AFMCO and contributors
// Regression guard for the barrel entry (components/index.js). A component that imports
// a PORTAL-LOCAL alias — "@/i18n", whose exports differ per portal — must never be
// re-exported here: a name-import from "@shared/components" would then fail `vite build`
// in every portal that lacks the export (this broke A-041 shell imports for fleet,
// route_supervisor, driver and safety). The explicit export list below is the guard; it
// fails the moment a new name appears without someone deciding it belongs.
import { describe, it, expect } from "vitest";
import * as barrel from "@shared/components/index.js";

describe("components barrel", () => {
  it("exports only portal-agnostic pieces", () => {
    expect(Object.keys(barrel).sort()).toEqual([
      "ActionDock",
      "AsyncBoundary",
      "Brand",
      "DataLedger",
      "DecisionStage",
      // EmptyState takes its text as props and imports nothing portal-local, so a
      // name-import from this barrel still resolves in every portal.
      "EmptyState",
      "EvidenceRail",
      "FleetPageShell",
      "IconBase",
      "LangToggle",
      "MetricRibbon",
      "MobileConsoleShell",
      "StatusLabel",
      "TabletSupervisorShell",
      "WorkQueue",
    ]);
  });
});
