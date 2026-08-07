// Copyright (c) 2026, afmcoltd
import { computed, ref } from "vue";
import { call } from "@shared/call";

const config = ref({ enabled: false, vapid_public_key: "", subscribed: false });
const subscribed = ref(false);
const busy = ref(false);
const denied = ref(false);

export function isPushSupported() {
  return (
    typeof navigator !== "undefined" &&
    "serviceWorker" in navigator &&
    typeof window !== "undefined" &&
    "PushManager" in window &&
    "Notification" in window
  );
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

function subKeys(sub) {
  const json = sub.toJSON();
  return { p256dh: json.keys?.p256dh || null, auth: json.keys?.auth || null };
}

export async function initPush() {
  if (!isPushSupported()) return;
  try {
    const cfg = await call("apex.salis.api.driver_portal.get_push_config");
    config.value = cfg || { enabled: false };
    if (config.value.enabled) {
      const reg = await navigator.serviceWorker.ready;
      const existing = await reg.pushManager.getSubscription();
      subscribed.value = !!existing && !!config.value.subscribed;
    }
  } catch (e) {
    config.value = { enabled: false };
  }
}

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
    await call("apex.salis.api.driver_portal.save_push_subscription", {
      type: "POST",
      args: { endpoint: sub.endpoint, p256dh, auth, user_agent: navigator.userAgent },
    });
    subscribed.value = true;
    return true;
  } catch (e) {
    return false;
  } finally {
    busy.value = false;
  }
}

export async function disablePush() {
  if (busy.value) return false;
  busy.value = true;
  try {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (sub) {
      await call("apex.salis.api.driver_portal.delete_push_subscription", {
        type: "POST",
        args: { endpoint: sub.endpoint },
      }).catch(() => {});
      await sub.unsubscribe().catch(() => {});
    }
    subscribed.value = false;
    return true;
  } finally {
    busy.value = false;
  }
}

export const canOfferPush = computed(() => isPushSupported() && config.value.enabled);
export const isSubscribed = computed(() => subscribed.value);
export const isBusy = computed(() => busy.value);
export const isDenied = computed(() => denied.value);
