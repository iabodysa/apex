// Copyright (c) 2026, AFMCO and contributors
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

// 1024px is --bp-desktop (frontend_shared/tokens.css); a CSS @media condition cannot read a
// custom property, so the two are kept in sync by hand and DESIGN.md §3 carries the widths.
export function useDesktop() {
  return useMediaQuery("(min-width: 1024px)");
}
