// Copyright (c) 2026, afmcoltd
import { reactive, ref, computed } from "vue";

export function useVehiclePanel(vehicles) {
  const panel = reactive({ open: false, plate: "", tab: 0, vehicle: null });
  const subForm = ref(null);

  function openPanel(plate, tab = 0) {
    const v = vehicles.value.find((x) => x.plate === plate);
    if (!v) return;
    panel.vehicle = v;
    panel.plate = plate;
    panel.tab = tab;
    panel.open = true;
    subForm.value = null;
  }
  function closePanel() {
    panel.open = false;
    panel.vehicle = null;
    panel.plate = "";
    subForm.value = null;
  }
  function setPTab(idx) {
    panel.tab = idx;
    subForm.value = null;
  }

  const tabDmg = computed(() => (panel.vehicle?.damages || []).length);
  const tabAcc = computed(() => (panel.vehicle?.accidents || []).length);

  return { panel, subForm, openPanel, closePanel, setPTab, tabDmg, tabAcc };
}
