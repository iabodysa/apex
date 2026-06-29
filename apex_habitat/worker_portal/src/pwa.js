// Copyright (c) 2026, AFMCO and contributors
// PWA new-build detection for the Masar SPA. The SW (registered by
// www/masar.html at root scope) installs a new build as a WAITING worker (no
// auto-skipWaiting); we flip `updateReady` so the shell shows a reload banner,
// and `applyUpdate()` tells the waiting worker to take over and reloads.

import { ref } from "vue";

export const updateReady = ref(false);

let waitingWorker = null;
let reloading = false;
// Reload on controllerchange ONLY after the worker tapped reload. A fresh SW
// claiming a previously-uncontrolled page also fires controllerchange (first
// load) — reloading then would be a spurious refresh.
let updateRequested = false;

// Re-check for a new build hourly and whenever the worker refocuses the tab, so
// a deploy is surfaced without waiting for a manual reload.
const UPDATE_POLL_MS = 60 * 60 * 1000;

function trackInstalling(reg, worker) {
  if (!worker) return;
  worker.addEventListener("statechange", () => {
    // A worker reaching "installed" while one already controls the page means a
    // NEW build is ready (the first-ever install has no controller — not an
    // update). reg.waiting is the worker to activate on reload.
    if (worker.state === "installed" && navigator.serviceWorker.controller) {
      waitingWorker = reg.waiting || worker;
      updateReady.value = true;
    }
  });
}

// Returns a teardown fn that clears the interval and removes every listener it
// added, so a caller can stop it in onUnmounted — this prevents a duplicate
// poll/listener set from stacking on HMR re-init (the App root re-running setup).
export function initPwaUpdates() {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) {
    return () => {};
  }

  let pollTimer = null;
  let onFocus = null;
  let onVisibility = null;

  navigator.serviceWorker.ready
    .then((reg) => {
      // A worker may already be waiting (installed before this tab loaded).
      if (reg.waiting && navigator.serviceWorker.controller) {
        waitingWorker = reg.waiting;
        updateReady.value = true;
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

  // When the new worker takes control AFTER the worker tapped reload, reload
  // once so the page is served by the new build. Ignore the first-load claim.
  const onControllerChange = () => {
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

export function applyUpdate() {
  updateRequested = true;
  if (!waitingWorker) {
    // No tracked waiting worker (e.g. it activated already) — a reload still
    // lands the latest build under the network-first shell.
    window.location.reload();
    return;
  }
  waitingWorker.postMessage({ type: "SKIP_WAITING" });
}
