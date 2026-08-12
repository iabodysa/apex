import { readonly, ref } from "vue";

const activeBuilding = ref("");

export const building = readonly(activeBuilding);
export function selectBuilding(name) {
  activeBuilding.value = typeof name === "string" ? name : "";
}
