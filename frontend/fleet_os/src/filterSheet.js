// Copyright (c) 2026, afmcoltd
import { ref } from "vue";

const sheetOpen = ref(false);

export function useFilterSheet() {
  return { sheetOpen };
}
