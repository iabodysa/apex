// Copyright (c) 2026, afmcoltd
import { computed, ref } from "vue";

const DISMISS_KEY = "salis_portal_install_dismissed";

const deferredPrompt = ref(null);
const dismissed = ref(readDismissed());

function readDismissed() {
  try {
    return localStorage.getItem(DISMISS_KEY) === "1";
  } catch (e) {
    return false;
  }
}

export function isStandalone() {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    window.navigator.standalone === true
  );
}

export function initPwa() {
  if (typeof window === "undefined") return;
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredPrompt.value = e;
  });
  window.addEventListener("appinstalled", () => {
    deferredPrompt.value = null;
    dismissInstallHint();
  });
}

export function dismissInstallHint() {
  dismissed.value = true;
  try {
    localStorage.setItem(DISMISS_KEY, "1");
  } catch (e) {
  }
}

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

export const canPrompt = computed(() => !!deferredPrompt.value);
export const showInstallHint = computed(() => !isStandalone() && !dismissed.value);
