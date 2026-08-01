// Copyright (c) 2026, AFMCO and contributors
// Read a selected image into the existing credential-scoped POST payload. The
// server validates it and creates the private File on the newly owned record.
import { isAcceptedPhoto } from "@shared/photoFile.js";

// Thrown when the pick cannot pass the server's type gate, so the caller can say
// WHICH formats are taken instead of showing a generic read failure.
export class UnsupportedPhotoType extends Error {}

export function readPhotoFile(file) {
  if (!file) return Promise.resolve({ photo: null, photo_filename: null });
  // Refuse before the upload, not after: `accept` is only a picker hint.
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
