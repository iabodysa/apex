// Copyright (c) 2026, afmcoltd
import { onMounted, onUnmounted } from "vue";

const DEFAULT_INTERVAL = 45000;

export function usePoll(refetch, interval = DEFAULT_INTERVAL) {
  let timer = null;
  let inFlight = false;

  function tick() {
    if (document.hidden || inFlight) return;
    inFlight = true;
    Promise.resolve()
      .then(() => refetch && refetch())
      .catch(() => {})
      .finally(() => {
        inFlight = false;
      });
  }

  function start() {
    if (timer) return;
    timer = setInterval(tick, interval);
  }

  function stop() {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }

  function onVisibility() {
    if (document.hidden) {
      stop();
    } else {
      tick();
      start();
    }
  }

  onMounted(() => {
    document.addEventListener("visibilitychange", onVisibility);
    if (!document.hidden) start();
  });

  onUnmounted(() => {
    document.removeEventListener("visibilitychange", onVisibility);
    stop();
  });

  return { stop, start };
}
