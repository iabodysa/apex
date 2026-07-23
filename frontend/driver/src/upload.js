// Copyright (c) 2026, AFMCO and contributors
// Read a selected image into the existing credential-scoped POST payload. The
// server validates it and creates the private File on the newly owned record.
export function readPhotoFile(file) {
  if (!file) return Promise.resolve({ photo: null, photo_filename: null });
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
