// Copyright (c) 2026, AFMCO and contributors
// PWA new-build detection for the Salis Driver SPA. The wiring lives in the
// shared factory (@shared/pwaUpdates.js); this file only instantiates it and
// re-exports the handles so App.vue keeps its `updateReady` / `applyUpdate` /
// `initPwaUpdates` imports. Driver updates activate and reload automatically;
// first installation remains reload-free because no prior controller exists.
import { createPwaUpdates } from "@shared/pwaUpdates.js";

export const { updateReady, initPwaUpdates, applyUpdate } = createPwaUpdates({
  autoActivate: true,
});
