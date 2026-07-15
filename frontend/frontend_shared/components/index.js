// Copyright (c) 2026, AFMCO and contributors
// Barrel entry for the shared portal component layer. Import the three archetype
// shells (and existing shared components) from one place:
//
//   import { FleetPageShell, MobileConsoleShell, TabletSupervisorShell } from "@shared/components";
//
// Direct-path imports (e.g. "@shared/components/FleetPageShell.vue") also work and
// are unchanged; this barrel is the documented package entry for the shell layer.
export { default as FleetPageShell } from "./FleetPageShell.vue";
export { default as MobileConsoleShell } from "./MobileConsoleShell.vue";
export { default as TabletSupervisorShell } from "./TabletSupervisorShell.vue";

// Existing shared presentational components.
export { default as Brand } from "./Brand.vue";
export { default as IconBase } from "./IconBase.vue";
export { default as LangToggle } from "./LangToggle.vue";
export { default as BuildingPicker } from "./BuildingPicker.vue";
