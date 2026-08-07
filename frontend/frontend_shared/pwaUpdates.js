// Copyright (c) 2026, afmcoltd
import { ref } from "vue";

const UPDATE_POLL_MS = 60 * 60 * 1000;

export function createPwaUpdates({ autoActivate = false } = {}) {
  const updateReady = ref(false);

  let waitingWorker = null;
  let reloading = false;
  let updateRequested = false;

  function trackInstalling(reg, worker) {
    if (!worker) return;
    worker.addEventListener("statechange", () => {
      if (!autoActivate && worker.state === "installed" && navigator.serviceWorker.controller) {
        waitingWorker = reg.waiting || worker;
        updateReady.value = true;
      }
    });
  }

  function initPwaUpdates() {
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) {
      return () => {};
    }

    const controlledAtStart = !!navigator.serviceWorker.controller;
    let pollTimer = null;
    let onFocus = null;
    let onVisibility = null;

    navigator.serviceWorker.ready
      .then((reg) => {
        if (reg.waiting && navigator.serviceWorker.controller) {
          if (autoActivate) {
            reg.waiting.postMessage({ type: "SKIP_WAITING" });
          } else {
            waitingWorker = reg.waiting;
            updateReady.value = true;
          }
        }
        reg.addEventListener("updatefound", () => trackInstalling(reg, reg.installing));

        const poll = () => reg.update().catch(() => {});
        pollTimer = setInterval(poll, UPDATE_POLL_MS);
        onFocus = poll;
        onVisibility = () => {
          if (document.visibilityState === "visible") poll();
        };
        window.addEventListener("focus", onFocus);
        document.addEventListener("visibilitychange", onVisibility);
      })
      .catch(() => {});

    const onControllerChange = () => {
      if (autoActivate && controlledAtStart && !reloading) {
        reloading = true;
        window.location.reload();
        return;
      }
      if (!updateRequested || reloading) return;
      reloading = true;
      window.location.reload();
    };
    navigator.serviceWorker.addEventListener("controllerchange", onControllerChange);

    return () => {
      if (pollTimer) clearInterval(pollTimer);
      if (onFocus) window.removeEventListener("focus", onFocus);
      if (onVisibility) document.removeEventListener("visibilitychange", onVisibility);
      navigator.serviceWorker.removeEventListener("controllerchange", onControllerChange);
    };
  }

  function applyUpdate() {
    updateRequested = true;
    if (!waitingWorker) {
      window.location.reload();
      return;
    }
    waitingWorker.postMessage({ type: "SKIP_WAITING" });
  }

  return { updateReady, initPwaUpdates, applyUpdate };
}
