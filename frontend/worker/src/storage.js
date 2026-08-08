// Copyright (c) 2026, afmcoltd
import { ref } from "vue";

import { purgePayloadStorage } from "@shared/driverStorage";

const LEGACY_PAYLOAD_PREFIX = "masar_portal_cache:";

if (typeof localStorage !== "undefined") {
  purgePayloadStorage(localStorage, LEGACY_PAYLOAD_PREFIX);
}

export const online = ref(typeof navigator === "undefined" ? true : navigator.onLine);

if (typeof window !== "undefined") {
  window.addEventListener("online", () => (online.value = true));
  window.addEventListener("offline", () => (online.value = false));
}
