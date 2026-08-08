// Copyright (c) 2026, afmcoltd
import { ref } from "vue";

const DENSITY_KEY = "fleet_portal_density";
const MODES = ["comfortable", "compact"];

/* How tightly the cards pack is a preference of this screen on this device, so it stays in
   local storage rather than the address: a link shared with a colleague should carry what he
   is meant to look at, not how closely this reader likes to sit to it. */
function initial() {
  try {
    const saved = localStorage.getItem(DENSITY_KEY);
    if (MODES.includes(saved)) return saved;
  } catch (e) {
    /* storage can be disabled; the board still opens */
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
      /* storage can be disabled; the choice simply does not persist */
    }
  }
  return { density, toggle };
}
