// Copyright (c) 2026, afmcoltd
import { computed, ref } from "vue";

/* Selection stays in memory on purpose. It is the one piece of board state nobody expects to
   survive a refresh, and a list of plates in the address would make a shared link act on the
   receiver's fleet rather than show him the sender's view. */
export function useSelection(filtered) {
  const selectMode = ref(false);
  const selected = ref(new Set());
  const selectedCount = computed(() => selected.value.size);
  const isSelected = (plate) => selected.value.has(plate);

  function toggleSelect(plate) {
    const next = new Set(selected.value);
    if (next.has(plate)) next.delete(plate);
    else next.add(plate);
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
    () => filtered.value.length > 0 && filtered.value.every((v) => selected.value.has(v.plate)),
  );
  function toggleSelectAll() {
    if (allVisibleSelected.value) clearSelection();
    else selected.value = new Set(filtered.value.map((v) => v.plate));
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
    toggleSelectAll,
  };
}
