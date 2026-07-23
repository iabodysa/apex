// Copyright (c) 2026, AFMCO and contributors
// Opt-in multi-select for bulk actions. Cards stay click-to-open by default; a
// toolbar toggle enters selection mode, and picked plates drive the bulk bar +
// the two bulk endpoints. Select-all spans only the currently filtered list.
import { ref, computed } from "vue";

export function useSelection(filtered) {
  const selectMode = ref(false);
  const selected = ref(new Set());
  const selectedCount = computed(() => selected.value.size);
  const isSelected = (plate) => selected.value.has(plate);

  function toggleSelect(plate) {
    const next = new Set(selected.value);
    next.has(plate) ? next.delete(plate) : next.add(plate);
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
    () => filtered.value.length > 0 && filtered.value.every((v) => selected.value.has(v.plate))
  );
  function toggleSelectAll() {
    if (allVisibleSelected.value) clearSelection();
    else selected.value = new Set(filtered.value.map((v) => v.plate));
  }

  return {
    selectMode, selected, selectedCount, isSelected,
    toggleSelect, clearSelection, toggleSelectMode,
    allVisibleSelected, toggleSelectAll,
  };
}
