// Copyright (c) 2026, afmcoltd
import { computed } from "vue";
import { createResource } from "frappe-ui";

/* One context for the whole app. The shell gate, the realtime room and the staff
   fallback all read the same answer. The SPA sends no credential — identity is the
   httpOnly cookie `apex/www/driver.py` set before it redirected to the clean path. */

let resource = null;

export function driverContext() {
  if (!resource) {
    resource = createResource({
      url: "apex.salis.api.driver_portal.get_driver_context",
      method: "GET",
      auto: true,
    });
  }
  return resource;
}

export const realtimeRoom = computed(() => driverContext().data?.realtime_room || "");
