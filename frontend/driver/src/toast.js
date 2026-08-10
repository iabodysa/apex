// Copyright (c) 2026, afmcoltd
import { toast } from "frappe-ui";

export function pushToast(message, kind = "ok", ttl) {
  if (!message) return;
  return toast.create({
    message,
    type: kind === "err" ? "error" : "success",
    duration: (ttl ?? (kind === "err" ? 4000 : 2500)) / 1000,
  });
}

export function clearToasts() {
  toast.removeAll();
}
