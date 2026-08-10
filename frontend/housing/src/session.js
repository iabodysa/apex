// Copyright (c) 2026, afmcoltd
import { ref, watch } from "vue";

const STORAGE_KEY = "housing_portal_building";

function readStored() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { name: "", label: "" };
    const parsed = JSON.parse(raw);
    return { name: parsed.name || "", label: parsed.label || "" };
  } catch (e) {
    return { name: "", label: "" };
  }
}

const stored = readStored();

export const building = ref(stored.name);
export const buildingLabel = ref(stored.label);

export const countProgress = ref({ done: 0, total: 0 });

watch([building, buildingLabel], ([name, label]) => {
  try {
    if (name) localStorage.setItem(STORAGE_KEY, JSON.stringify({ name, label }));
    else localStorage.removeItem(STORAGE_KEY);
  } catch (storageUnavailable) {
    return;
  }
});

export function selectBuilding(name, label) {
  building.value = name;
  buildingLabel.value = label || name;
}

export function forgetMissingBuilding(error) {
  const text = String((error && (error.message || error.exc_type)) || error || "");
  if (!/DoesNotExist|not found/i.test(text)) return false;
  clearBuilding();
  return true;
}

export function clearBuilding() {
  building.value = "";
  buildingLabel.value = "";
  countProgress.value = { done: 0, total: 0 };
}

export function localDate() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
