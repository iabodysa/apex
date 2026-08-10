// Copyright (c) 2026, afmcoltd
import { computed } from "vue";
import { createResource } from "frappe-ui";

import { hasToken } from "./token.js";


let resource = null;

export function workerContext() {
  if (!resource) {
    resource = createResource({
      url: "apex.salis.api.masar.get_worker_context",
      method: "GET",
      auto: hasToken,
    });
  }
  return resource;
}

export const realtimeRoom = computed(() => workerContext().data?.realtime_room || "");
