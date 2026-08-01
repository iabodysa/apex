// Copyright (c) 2026, AFMCO and contributors
// The client half of the portal photo contract. `accept="image/*"` is a picker
// HINT — every browser lets the operator pick "All files" past it — so a .txt or a
// .gif reached the endpoint and came back as a server refusal the operator could
// not act on. The server decides on the BYTES
// (apex/salis/api/driver_portal/images.py::verified_image_type) and takes exactly
// JPEG / PNG / WebP; GIF, HEIC and HEIF are refused there. This file is the one
// place that set is written on the client, so the two doors cannot drift.
//
// Shared because three pickers in two portals feed the same two endpoints: the
// driver shift photo, the driver ticket photo and the Masar request photo.

// `accept` value for the <input type="file">. Explicit types, not "image/*": the
// picker then defaults to only what the server will actually take.
export const PHOTO_ACCEPT = "image/jpeg,image/png,image/webp";

// The extensions the server maps to a content type (images.py `_IMAGE_TYPES`).
const EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"];
const TYPES = ["image/jpeg", "image/png", "image/webp"];

// true when the file can pass the server's type gate. Both halves are checked
// because the server keys the expected type off the FILENAME extension and then
// verifies the bytes against it, and because some platforms hand back an empty
// `file.type` for a perfectly valid pick.
export function isAcceptedPhoto(file) {
  if (!file) return false;
  const name = String(file.name || "").toLowerCase();
  if (!EXTENSIONS.some((ext) => name.endsWith(ext))) return false;
  const type = String(file.type || "").toLowerCase();
  return !type || TYPES.includes(type);
}
