// Copyright (c) 2026, afmcoltd
import { computed } from "vue";
import { createResource } from "frappe-ui";

import { hasToken } from "./token.js";

/* One shell context for the whole app: the header, the Profile screen and the realtime
   room all read the same answer, so a second copy could disagree with the first. The
   SPA sends no credential — `_token_from_request` resolves the httpOnly cookie. */

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
