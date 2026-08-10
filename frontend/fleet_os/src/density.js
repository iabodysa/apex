// Copyright (c) 2026, afmcoltd
import { ref } from "vue";

const DENSITY_KEY = "fleet_portal_density";
const MODES = ["comfortable", "compact"];

function initial() {
  try {
    const saved = localStorage.getItem(DENSITY_KEY);
    if (MODES.includes(saved)) return saved;
  } catch (e) {
  }
  return MODES[0];
}

const density = ref(initial());

export function useDensity() {
  function toggle() {
    density.value = density.value === "compact" ? "comfortable" : "compact";
    try {
      localStorage.setItem(DENSITY_KEY, density.value);
    } catch (e) {
    }
  }
  return { density, toggle };
}
