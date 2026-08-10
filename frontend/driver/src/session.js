// Copyright (c) 2026, afmcoltd
import { computed } from "vue";
import { createResource } from "frappe-ui";


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
