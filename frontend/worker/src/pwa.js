// Copyright (c) 2026, AFMCO and contributors
// PWA new-build detection for the Masar (worker) SPA. The wiring lives in the
// shared factory (@shared/pwaUpdates.js); this file only instantiates it and
// re-exports the handles so App.vue keeps its `updateReady` / `applyUpdate` /
// `initPwaUpdates` imports. The factory default already matches this portal's
// original controllerchange guard (reload only after applyUpdate()).
import { createPwaUpdates } from "@shared/pwaUpdates.js";

export const { updateReady, initPwaUpdates, applyUpdate } = createPwaUpdates();
