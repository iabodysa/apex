# Copyright (c) 2026, afmcoltd

_PORTAL_PAGES = frozenset(
    path
    for route in (
        "/masar",
        "/driver",
        "/masar-supervisor",
        "/fleet",
        "/fleet-os",
        "/housing",
        "/safety",
    )
    for path in (route, f"{route}/")
)

_PRIVATE_API_PREFIXES = (
    "/api/method/apex.salis.api.",
    "/api/method/apex.habitat.api.",
    "/api/method/apex.apex_core.doctype.masar_worker_token.",
)

_WORKER_SCOPES = {
    "/masar-sw.min.js": "/masar/",
    "/driver-sw.min.js": "/driver/",
}


def apply_portal_response_headers(response, request):
    path = request.path
    if not _is_private_portal_path(path):
        return

    response.headers["Cache-Control"] = "no-store, private, max-age=0"
    response.headers["Pragma"] = "no-cache"
    _append_vary_cookie(response.headers)

    worker_scope = _WORKER_SCOPES.get(path)
    if worker_scope:
        response.headers["Service-Worker-Allowed"] = worker_scope


def _is_private_portal_path(path):
    return (
        path in _PORTAL_PAGES
        or path in _WORKER_SCOPES
        or path.startswith(_PRIVATE_API_PREFIXES)
    )


def _append_vary_cookie(headers):
    values = []
    seen = set()
    for header_value in headers.getlist("Vary"):
        for value in header_value.split(","):
            value = value.strip()
            if value and value.casefold() not in seen:
                values.append(value)
                seen.add(value.casefold())
    if "cookie" not in seen:
        values.append("Cookie")
    headers["Vary"] = ", ".join(values)
