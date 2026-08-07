// Copyright (c) 2026, afmcoltd

export const PHOTO_ACCEPT = "image/jpeg,image/png,image/webp";

const EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"];
const TYPES = ["image/jpeg", "image/png", "image/webp"];

export function isAcceptedPhoto(file) {
  if (!file) return false;
  const name = String(file.name || "").toLowerCase();
  if (!EXTENSIONS.some((ext) => name.endsWith(ext))) return false;
  const type = String(file.type || "").toLowerCase();
  return !type || TYPES.includes(type);
}
