// Copyright (c) 2026, afmcoltd
import { ref } from "vue";

/* Whether the filter rail is showing as a sheet on a narrow screen. Deliberately NOT in the
   address: it is a way of reaching the filters on a small screen, not a filter itself, and a
   link that reopened someone else's sheet would be noise. */
const sheetOpen = ref(false);

export function useFilterSheet() {
  return { sheetOpen };
}
