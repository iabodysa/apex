// Copyright (c) 2026, afmcoltd
import { onUnmounted, ref } from "vue";

export function useMediaQuery(query) {
  const matches = ref(false);
  if (typeof window === "undefined" || !window.matchMedia) return matches;

  const mql = window.matchMedia(query);
  matches.value = mql.matches;
  const onChange = (e) => {
    matches.value = e.matches;
  };
  mql.addEventListener("change", onChange);
  onUnmounted(() => mql.removeEventListener("change", onChange));
  return matches;
}

export function useDesktop() {
  return useMediaQuery("(min-width: 1024px)");
}
