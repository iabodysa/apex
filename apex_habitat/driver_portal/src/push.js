// Copyright (c) 2026, AFMCO and contributors
// Web Push opt-in for the driver portal: lets the server deliver a background push
// ("trip assigned", "fuel approved") to a driver whose app is closed.
// The toggle appears only when all three hold (else hidden — no-op-until-wired):
// browser Push API support, server reports push configured, and the SW is active.
// Secrets stay server-side: the SPA only handles the PUBLIC VAPID key.
import { computed, ref } from "vue";
import { frappeRequest } from "frappe-ui";

// Server-reported config (set on init): is push configured + the public VAPID key.
const config = ref({ enabled: false, vapid_public_key: "", subscribed: false });
// True once this device holds a live browser subscription (after opt-in).
const subscribed = ref(false);
// In-flight flag so the UI can disable the toggle during subscribe/unsubscribe.
const busy = ref(false);
// Browser permission was explicitly denied — the UI then explains how to re-enable.
const denied = ref(false);

// The Push API needs both service workers and PushManager; older/embedded webviews
// (and iOS before 16.4 outside standalone) lack one, so we degrade to no affordance.
export function isPushSupported() {
  return (
    typeof navigator !== "undefined" &&
    "serviceWorker" in navigator &&
    typeof window !== "undefined" &&
    "PushManager" in window &&
    "Notification" in window
  );
}

// applicationServerKey must be a Uint8Array; the server hands us the standard
// base64url VAPID public key, so decode it here.
function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

// Read a PushSubscription's keys as base64 strings for the server payload.
function subKeys(sub) {
  const json = sub.toJSON();
  return { p256dh: json.keys?.p256dh || null, auth: json.keys?.auth || null };
}

// Load the server's push config and reflect any existing subscription. Safe to call
// on app start: a friendly {enabled:false} (push off/unconfigured, or not a linked
// driver) simply leaves the toggle hidden — it never throws into the UI.
export async function initPush() {
  if (!isPushSupported()) return;
  try {
    const cfg = await frappeRequest({
      url: "/api/method/apex_habitat.salis.api.driver_portal.get_push_config",
    });
    config.value = cfg || { enabled: false };
    if (config.value.enabled) {
      const reg = await navigator.serviceWorker.ready;
      const existing = await reg.pushManager.getSubscription();
      subscribed.value = !!existing && !!config.value.subscribed;
    }
  } catch (e) {
    // Push config unavailable — leave the affordance hidden, never block boot.
    config.value = { enabled: false };
  }
}

// Opt this device in: request permission, subscribe via the SW's PushManager, then
// POST the subscription to the server. Returns true on success. A denied permission
// flips `denied` (the UI explains re-enabling) rather than throwing.
export async function enablePush() {
  if (!isPushSupported() || !config.value.enabled || busy.value) return false;
  busy.value = true;
  try {
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      denied.value = permission === "denied";
      return false;
    }
    denied.value = false;
    const reg = await navigator.serviceWorker.ready;
    const sub =
      (await reg.pushManager.getSubscription()) ||
      (await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(config.value.vapid_public_key),
      }));
    const { p256dh, auth } = subKeys(sub);
    await frappeRequest({
      url: "/api/method/apex_habitat.salis.api.driver_portal.save_push_subscription",
      method: "POST",
      params: { endpoint: sub.endpoint, p256dh, auth, user_agent: navigator.userAgent },
    });
    subscribed.value = true;
    return true;
  } catch (e) {
    return false;
  } finally {
    busy.value = false;
  }
}

// Opt this device out: unsubscribe the browser and disable the server row. Best-effort
// on both sides so a partial failure still leaves the toggle off.
export async function disablePush() {
  if (busy.value) return false;
  busy.value = true;
  try {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (sub) {
      await frappeRequest({
        url: "/api/method/apex_habitat.salis.api.driver_portal.delete_push_subscription",
        method: "POST",
        params: { endpoint: sub.endpoint },
      }).catch(() => {});
      await sub.unsubscribe().catch(() => {});
    }
    subscribed.value = false;
    return true;
  } finally {
    busy.value = false;
  }
}

// Show the opt-in only when supported AND the server says push is configured.
export const canOfferPush = computed(() => isPushSupported() && config.value.enabled);
export const isSubscribed = computed(() => subscribed.value);
export const isBusy = computed(() => busy.value);
export const isDenied = computed(() => denied.value);
