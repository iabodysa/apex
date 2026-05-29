# Integration Guide

This guide explains how to integrate an external frontend with **apex_habitat**, a [Frappe Framework](https://frappeframework.com/) v15 application. It is a developer starter kit: install the backend, authenticate, and start consuming the API from any stack.

## 1. The backend / frontend model

apex_habitat is a **backend** and the single source of truth. It owns the data model, authentication, permissions, business logic, workflows, and scheduled jobs.

A **frontend** is any client that consumes this backend over HTTP. It is presentation only: it renders data and calls the API, but it never modifies the backend or its logic. Because all data, permissions, and workflow rules are enforced server-side, the client cannot weaken them.

The frontend is **stack-agnostic**. It can be React, Vue, Angular, Svelte, Flutter, a native iOS/Android app, or a server-side service - anything that can send HTTP requests with a header. The two sides integrate through a clean, versioned HTTP contract, not by sharing code.

```
+------------------+        HTTP + token auth        +-----------------------------+
|  Your frontend   |  ---------------------------->  |  apex_habitat (Frappe v15)  |
|  (any stack)     |  <----------------------------  |  data, auth, logic, workflow|
+------------------+          JSON responses         +-----------------------------+
```

## 2. Install the backend

apex_habitat runs on a Frappe v15 bench and site. Its `required_apps` are **frappe**, **erpnext**, and **hrms**, so those must be installed on the same site.

```bash
# Prerequisites: a Frappe v15 bench + site, with erpnext and hrms installed.
bench get-app https://github.com/iabodysa/apex --branch apex
bench --site <your-site> install-app apex_habitat
bench --site <your-site> migrate
```

After `migrate` completes, the DocTypes, permissions, workflows, and seed data are available, and the API is ready to use.

## 3. Authentication - API token (key + secret)

Because the frontend lives on a **different origin** from the backend, use Frappe's **API key / secret token** authentication. Do not rely on cookie/session login from a separate origin.

### Generate a key and secret

1. In the backend, open the **User** record for the integration account.
2. Open the **API Access** section and click **Generate Keys**.
3. Copy the **API Key** (shown on the user) and the **API Secret** (shown once at generation time - store it securely).

### Send the token on every request

Add this header to every API call:

```
Authorization: token <api_key>:<api_secret>
```

### Why token auth (and not session / CSRF)

- **Stateless**: each request carries its own credentials. There is no login round-trip and no server-side session to keep alive.
- **CSRF-exempt**: token-authenticated requests do not require a CSRF token. Session/cookie requests from another origin do require one, and a missing or stale CSRF token produces an HTTP `400` - a common and confusing failure for cross-origin clients. Token auth sidesteps this entirely.
- **Reliable from an external origin**: a plain `fetch`/`axios`-style client works without a framework-specific SDK.

Operational notes:

- Use **HTTPS** only - the token is a bearer credential.
- **Scope keys per role**: create a dedicated user (or users) for the frontend and assign only the roles it needs. Permissions and project scoping are enforced server-side per user.
- **Rotate / revoke** keys as needed by regenerating them on the User record.

## 4. CORS

The browser blocks cross-origin requests unless the backend allows the frontend's origin. Add the frontend origin to `allow_cors` in the site's `site_config.json`:

```json
{
  "allow_cors": "https://your-frontend.example.com"
}
```

To allow more than one origin (for example a production and a development origin), use a list:

```json
{
  "allow_cors": ["https://your-frontend.example.com", "http://localhost:3000"]
}
```

> The in-app **Apex Integration Settings** record has an **Allowed Origins** field where an administrator can record the intended origin(s). That field is documentation only; it does not modify `site_config.json`. Set `allow_cors` yourself as shown above.

## 5. API surface

### 5.1 Generic REST - `/api/resource/<DocType>`

Frappe exposes every DocType through a generic REST endpoint that supports list, filter, get, create, and update. Every call is governed automatically by the user's permissions and by project row-scoping, so a client only ever sees what its roles allow.

| Operation | Method | Path |
|-----------|--------|------|
| List / filter | `GET` | `/api/resource/<DocType>` |
| Get one | `GET` | `/api/resource/<DocType>/<name>` |
| Create | `POST` | `/api/resource/<DocType>` |
| Update | `PUT` | `/api/resource/<DocType>/<name>` |

Example - list `Transport Request` records filtered by service line, returning selected fields:

```
GET /api/resource/Transport Request?filters=[["service_line","=","Workers"]]&fields=["name","service_line","status"]
```

Filters use Frappe's list syntax (`[[fieldname, operator, value], ...]`, URL-encoded). `fields`, `limit_page_length`, `limit_start`, and `order_by` are also supported.

### 5.2 Whitelisted RPC - `/api/method/<dotted.path>`

Purpose-built endpoints are exposed as whitelisted methods. Call them at `/api/method/<dotted.path>` with arguments as query parameters (`GET`) or a JSON/form body (`POST`). Available endpoints include:

- **Driver portal** - `apex_habitat.salis.api.driver_portal.*`
  (driver context, today's trips, support tickets, check-in / check-out, fuel-request submission, and support-ticket creation).
- **Dispatch board** - `apex_habitat.salis.api.dispatch_board.*`
  (the dispatch board view: vehicles, trips, drivers, and transport requests, optionally scoped by project).
- **Fuel console** - `apex_habitat.salis.api.fuel_console.get_pending_fuel_requests`, `apex_habitat.salis.api.fuel_console.approve_fuel_request`, `apex_habitat.salis.api.fuel_console.reject_fuel_request`.

These endpoints enforce the same roles, permissions, and project scoping as the rest of the backend.

### 5.3 Driving workflows - `apply_workflow`

Documents that use a workflow are advanced through the native workflow engine rather than by writing the status field directly. Call:

```
POST /api/method/frappe.model.workflow.apply_workflow
```

with the document and the action to apply. Role checks and segregation-of-duties rules are enforced server-side, so a client button can never bypass them.

```jsonc
// form / JSON body
{
  "doc": { "doctype": "Transport Request", "name": "TR-0001", /* ...current doc... */ },
  "action": "Approve"
}
```

## 6. A minimal authenticated example

### curl

```bash
curl -X GET \
  'https://your-backend.example.com/api/resource/Transport Request?filters=[["service_line","=","Workers"]]&fields=["name","service_line","status"]' \
  -H 'Authorization: token <api_key>:<api_secret>' \
  -H 'Accept: application/json'
```

### JavaScript (`fetch`)

```js
const BASE = "https://your-backend.example.com";
const TOKEN = "token <api_key>:<api_secret>"; // load from secure config, never hard-code

async function listWorkerTransportRequests() {
  const filters = encodeURIComponent('[["service_line","=","Workers"]]');
  const fields = encodeURIComponent('["name","service_line","status"]');
  const res = await fetch(
    `${BASE}/api/resource/Transport Request?filters=${filters}&fields=${fields}`,
    {
      method: "GET",
      headers: {
        Authorization: TOKEN,
        Accept: "application/json",
      },
    }
  );
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} ${res.statusText}`);
  }
  const { data } = await res.json();
  return data;
}
```

The same `Authorization: token <key>:<secret>` header works for every endpoint in Section 5, on any HTTP client. The pattern is identical whether you use `fetch`, `axios`, a mobile HTTP library, or a backend-to-backend call.

## 7. Versioned contract

The documented endpoints and their request/response shapes are treated as a **public interface** with a contract version (see **API Contract Version** in **Apex Integration Settings**).

- **Additive changes are safe** - new endpoints, new optional fields, and new optional parameters do not break existing clients.
- **Breaking changes require a version bump and a notice** - renaming or removing an endpoint or field, changing a response shape, or making a parameter newly required increments the contract version, and integrators are notified ahead of the change.

Build the frontend against a known contract version and treat unexpected breaking changes as a backend issue (see Section 8).

## 8. Reporting integration issues

The frontend and backend live in separate repositories, and the frontend does not edit the backend. When you hit a backend-side integration problem - a missing endpoint, an unexpected `4xx`/`5xx`, a field you need, or a CORS/auth issue - open an issue on the backend repository:

**https://github.com/iabodysa/apex/issues**

Include:

- **Endpoint** - the method and path you called.
- **Request** - headers (redact the secret), parameters, and body.
- **Expected** - what you expected to happen.
- **Actual** - the status code and the response body you received.

Clear, reproducible reports are triaged, fixed in the backend, and released; you then pull and re-test against the updated contract.
