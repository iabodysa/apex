// Copyright (c) 2026, AFMCO and contributors
// PWA new-build detection for the Salis Driver SPA. The wiring lives in the
// shared factory (@shared/pwaUpdates.js); this file only instantiates it and
// re-exports the handles so App.vue keeps its `updateReady` / `applyUpdate` /
// `initPwaUpdates` imports. NOTE: the shared factory carries the worker/Masar
// portal's safer controllerchange guard (reload only after applyUpdate()), which
// fixes a latent first-load spurious-refresh this portal used to have.
import { createPwaUpdates } from "@shared/pwaUpdates.js";

export const { updateReady, initPwaUpdates, applyUpdate } = createPwaUpdates();
