// Copyright (c) 2026, AFMCO and contributors
// Regression guard for the barrel entry (components/index.js). BuildingPicker
// imports `resourceErrorMessage` from the portal-local "@/i18n" — an export only
// some portals' i18n.js provide — so re-exporting it here would make any
// name-import from "@shared/components" fail `vite build` in portals that lack
// that export (this broke A-041 shell imports for fleet/route_supervisor/driver/
// safety). This test fails loudly if BuildingPicker (or any future component with
// the same kind of portal-specific dependency) is added back to the barrel.
import { describe, it, expect } from "vitest";
import * as barrel from "@shared/components/index.js";

describe("components barrel", () => {
  it("exports only portal-agnostic pieces", () => {
    // ThemeToggle joins LangToggle here: its only portal-local import is `useI18n`,
    // which every portal's i18n.js exports, so a name-import from this barrel still
    // resolves everywhere. That is the admission test, not "it is shared".
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
      "PortalFrame",
      "StatusLabel",
      "TabletSupervisorShell",
      "ThemeToggle",
      "WorkQueue",
    ]);
  });

  it("does not re-export BuildingPicker", () => {
    expect(barrel.BuildingPicker).toBeUndefined();
  });
});
