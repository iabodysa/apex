// Copyright (c) 2026, AFMCO and contributors
// PWA install affordance state for the driver portal. Captures the browser's
// beforeinstallprompt event so the app can offer a real one-tap "Add to Home
// Screen" where supported (Chrome/Android), and falls back to a hint card
// elsewhere (iOS Safari has no programmatic prompt). Dismissal is persisted so
// the card shows once and stays gone.
import { computed, ref } from "vue";

const DISMISS_KEY = "salis_portal_install_dismissed";

// The deferred beforeinstallprompt event, when the browser fired one.
const deferredPrompt = ref(null);
// Whether the user dismissed the hint (persisted across visits).
const dismissed = ref(readDismissed());

function readDismissed() {
  try {
    return localStorage.getItem(DISMISS_KEY) === "1";
  } catch (e) {
    return false;
  }
}

// True when the app is already running installed (standalone display mode, or the
// iOS Safari standalone flag) — no install affordance needed.
export function isStandalone() {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    window.navigator.standalone === true
  );
}

// Wire the browser install events once, at app start. Capturing the event lets us
// trigger the native prompt later; appinstalled marks the hint done.
export function initPwa() {
  if (typeof window === "undefined") return;
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault(); // keep the event so we can prompt on the user's tap
    deferredPrompt.value = e;
  });
  window.addEventListener("appinstalled", () => {
    deferredPrompt.value = null;
    dismissInstallHint();
  });
}

// Persist the dismissal so the hint never nags again.
export function dismissInstallHint() {
  dismissed.value = true;
  try {
    localStorage.setItem(DISMISS_KEY, "1");
  } catch (e) {
    // storage unavailable — the in-memory flag still hides it this session
  }
}

// Fire the captured native prompt (Chrome/Android). Resolves once the user
// accepts/dismisses; either way the hint is then dismissed.
export async function promptInstall() {
  const e = deferredPrompt.value;
  if (!e) return false;
  e.prompt();
  try {
    await e.userChoice;
  } finally {
    deferredPrompt.value = null;
    dismissInstallHint();
  }
  return true;
}

// Show the hint card when: not already installed, not dismissed. canPrompt drives
// whether to show an "Install" button (native prompt available) vs. manual steps.
export const canPrompt = computed(() => !!deferredPrompt.value);
export const showInstallHint = computed(() => !isStandalone() && !dismissed.value);
