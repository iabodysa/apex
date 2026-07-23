// Copyright (c) 2026, AFMCO and contributors
// Barrel entry for the shared portal component layer. Import the three archetype
// shells (and existing shared components) from one place:
//
//   import { FleetPageShell, MobileConsoleShell, TabletSupervisorShell } from "@shared/components";
//
// Direct-path imports (e.g. "@shared/components/FleetPageShell.vue") also work and
// are unchanged; this barrel is the documented package entry for the shell layer.
//
// BuildingPicker is deliberately NOT re-exported here. It imports
// `resourceErrorMessage` from the portal-local "@/i18n" (see BuildingPicker.vue),
// an export only some portals' i18n.js provide. Re-exporting it from this barrel
// would make `import { anything } from "@shared/components"` resolve "@/i18n" in
// every consuming portal, failing `vite build` for portals that lack that export
// (this broke A-041 name-imports for fleet/route_supervisor/driver/safety).
// BuildingPicker stays importable by direct path:
//   import BuildingPicker from "@shared/components/BuildingPicker.vue";
// as already used by housing/src/pages/Count.vue.
export { default as FleetPageShell } from "./FleetPageShell.vue";
export { default as MobileConsoleShell } from "./MobileConsoleShell.vue";
export { default as TabletSupervisorShell } from "./TabletSupervisorShell.vue";

// Existing shared presentational components. Brand/IconBase have no portal-local
// dependency; LangToggle only needs `useI18n` from "@/i18n", which every portal
// exports (unlike `resourceErrorMessage`), so all three are safe to barrel-export
// unlike BuildingPicker above.
export { default as Brand } from "./Brand.vue";
export { default as IconBase } from "./IconBase.vue";
export { default as LangToggle } from "./LangToggle.vue";
