// Copyright (c) 2026, afmcoltd

export async function cameraState() {
  if (typeof window === "undefined" || typeof navigator === "undefined") return "unsupported";
  if (!("BarcodeDetector" in window)) return "unsupported";
  if (window.isSecureContext === false) return "insecure";
  const media = navigator.mediaDevices;
  if (!media || typeof media.getUserMedia !== "function") return "unsupported";
  if (typeof media.enumerateDevices !== "function") return "ready";
  try {
    const devices = await media.enumerateDevices();
    return devices.some((device) => device.kind === "videoinput") ? "ready" : "absent";
  } catch (e) {
    return "absent";
  }
}

export function cameraFailure(error) {
  const name = (error && error.name) || "";
  if (name === "NotAllowedError" || name === "SecurityError") return "denied";
  if (name === "NotFoundError" || name === "DevicesNotFoundError" || name === "OverconstrainedError")
    return "absent";
  if (name === "NotReadableError" || name === "TrackStartError" || name === "AbortError")
    return "busy";
  return "failed";
}

export function onCameraChange(handler) {
  const media = typeof navigator !== "undefined" && navigator.mediaDevices;
  if (!media || typeof media.addEventListener !== "function") return () => {};
  media.addEventListener("devicechange", handler);
  return () => media.removeEventListener("devicechange", handler);
}
