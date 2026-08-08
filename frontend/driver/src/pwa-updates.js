// Copyright (c) 2026, afmcoltd
import { createPwaUpdates } from "@shared/pwaUpdates.js";

/* `autoActivate` takes the reload out of the driver's hands on purpose: paired with the
   service worker's skipWaitingOnInstall, it is what makes a security fix reach a phone
   that already has the app installed. Under that flag `updateReady` is never set, so
   there is no banner to export. */
export const { initPwaUpdates } = createPwaUpdates({ autoActivate: true });
