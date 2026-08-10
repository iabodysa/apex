// Copyright (c) 2026, afmcoltd
import { computed, ref } from "vue";

export const MAX_BULK_SELECTION = 50;

export function useSelection(filtered) {
  const selectMode = ref(false);
  const selected = ref(new Set());
  const selectedCount = computed(() => selected.value.size);
  const isSelected = (plate) => selected.value.has(plate);

  function toggleSelect(plate) {
    const next = new Set(selected.value);
    if (next.has(plate)) next.delete(plate);
    else if (next.size < MAX_BULK_SELECTION) next.add(plate);
    selected.value = next;
  }
  function clearSelection() {
    selected.value = new Set();
  }
  function toggleSelectMode() {
    selectMode.value = !selectMode.value;
    if (!selectMode.value) clearSelection();
  }
  const allVisibleSelected = computed(
    () =>
      filtered.value.length > 0 &&
      filtered.value.slice(0, MAX_BULK_SELECTION).every((v) => selected.value.has(v.plate)),
  );
  const selectionLimitReached = computed(
    () => selected.value.size >= MAX_BULK_SELECTION,
  );
  function toggleSelectAll() {
    if (allVisibleSelected.value) clearSelection();
    else selected.value = new Set(filtered.value.slice(0, MAX_BULK_SELECTION).map((v) => v.plate));
  }

  return {
    selectMode,
    selected,
    selectedCount,
    isSelected,
    toggleSelect,
    clearSelection,
    toggleSelectMode,
    allVisibleSelected,
    selectionLimitReached,
    maxSelection: MAX_BULK_SELECTION,
    toggleSelectAll,
  };
}
