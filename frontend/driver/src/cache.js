// Copyright (c) 2026, afmcoltd
import { ref } from "vue";
import { purgeDriverPayloadStorage } from "@shared/driverStorage";

if (typeof localStorage !== "undefined") purgeDriverPayloadStorage(localStorage);

const online = ref(typeof navigator === "undefined" ? true : navigator.onLine);
if (typeof window !== "undefined") {
  window.addEventListener("online", () => (online.value = true));
  window.addEventListener("offline", () => (online.value = false));
}

export { online };
