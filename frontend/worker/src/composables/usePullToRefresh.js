// Copyright (c) 2026, afmcoltd
import { onMounted, onUnmounted, ref } from "vue";

const THRESHOLD = 70;
const MAX_PULL = 110;
const RESISTANCE = 0.5;
const SLOP = 12;

export function usePullToRefresh(onRefresh) {
  const distance = ref(0);
  const refreshing = ref(false);
  const armed = ref(false);

  let startY = 0;
  let pulling = false;
  let scroller = null;

  function scrollerFor(target) {
    let node = target instanceof Element ? target : null;
    while (node) {
      const overflow = getComputedStyle(node).overflowY;
      if (
        (overflow === "auto" || overflow === "scroll") &&
        node.scrollHeight > node.clientHeight
      ) {
        return node;
      }
      node = node.parentElement;
    }
    return null;
  }

  function scrollTop() {
    return scroller ? scroller.scrollTop : window.scrollY;
  }

  function onTouchStart(e) {
    scroller = scrollerFor(e.target);
    if (!scroller || refreshing.value || scrollTop() > 0 || e.touches.length !== 1) {
      pulling = false;
      return;
    }
    startY = e.touches[0].clientY;
    pulling = true;
  }

  function onTouchMove(e) {
    if (!pulling || refreshing.value) return;

    const delta = e.touches[0].clientY - startY;

    if (delta <= 0 || scrollTop() > 0) {
      armed.value = false;
      distance.value = 0;
      pulling = false;
      return;
    }

    if (delta < SLOP) return;

    if (e.cancelable) e.preventDefault();

    armed.value = true;
    distance.value = Math.min(delta * RESISTANCE, MAX_PULL);
  }

  function onTouchEnd() {
    if (!pulling) return;
    pulling = false;

    if (!armed.value) {
      distance.value = 0;
      return;
    }
    armed.value = false;

    if (distance.value >= THRESHOLD) {
      refreshing.value = true;
      distance.value = THRESHOLD;
      Promise.resolve()
        .then(() => onRefresh && onRefresh())
        .catch(() => {})
        .finally(() => {
          refreshing.value = false;
          distance.value = 0;
        });
    } else {
      distance.value = 0;
    }
  }

  onMounted(() => {
    document.addEventListener("touchstart", onTouchStart, { passive: true });
    document.addEventListener("touchmove", onTouchMove, { passive: false });
    document.addEventListener("touchend", onTouchEnd, { passive: true });
    document.addEventListener("touchcancel", onTouchEnd, { passive: true });
  });

  onUnmounted(() => {
    document.removeEventListener("touchstart", onTouchStart);
    document.removeEventListener("touchmove", onTouchMove);
    document.removeEventListener("touchend", onTouchEnd);
    document.removeEventListener("touchcancel", onTouchEnd);
  });

  return { distance, refreshing, armed, THRESHOLD };
}
