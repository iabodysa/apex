// Copyright (c) 2026, afmcoltd
import { isAcceptedPhoto } from "@shared/photoFile.js";

export class UnsupportedPhotoType extends Error {}

export function readPhotoFile(file) {
  if (!file) return Promise.resolve({ photo: null, photo_filename: null });
  if (!isAcceptedPhoto(file)) {
    return Promise.reject(new UnsupportedPhotoType("Unsupported photo type."));
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve({
      photo: String(reader.result || ""),
      photo_filename: file.name,
    });
    reader.onerror = () => reject(reader.error || new Error("Unable to read photo."));
    reader.readAsDataURL(file);
  });
}
