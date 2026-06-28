// Copyright (c) 2026, AFMCO and contributors
// Single private-file upload helper, shared by the screens that capture a photo
// (Attendance check-in/out, Support ticket). Posts to Frappe's native upload_file
// endpoint with the CSRF token the page shell injects, and returns the new File's
// url (or null on failure) so the caller passes it as an already-uploaded url.
export async function uploadPrivateFile(file) {
  if (!file) return null;
  const fd = new FormData();
  fd.append("file", file, file.name);
  fd.append("is_private", 1);
  const res = await fetch("/api/method/upload_file", {
    method: "POST",
    headers: { "X-Frappe-CSRF-Token": window.csrf_token },
    body: fd,
  });
  const json = await res.json();
  return json.message?.file_url || null;
}
