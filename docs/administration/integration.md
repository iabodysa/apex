# Integration Guide

This guide covers third-party clients that communicate with an Apex site over
Frappe APIs. First-party portals are described in
[Frontend Architecture](frontend-architecture.md).

## Security boundary

Frappe provides authentication, DocPerm evaluation, and workflow execution.
Apex configures those primitives and adds row scope, domain validation, and
worker or driver token guards. A client may present actions and data, but it
must not reproduce or bypass those controls.

Choose authentication by client type:

| Client | Use | Keep in mind |
|---|---|---|
| Confidential server or backend-for-frontend | Dedicated Frappe User with API key and secret | Keep both credentials on the server, use least privilege, and rotate them. |
| Browser or distributed mobile application | Native Frappe OAuth authorization code with PKCE through an OAuth Client, or a backend-for-frontend | Never embed an API secret in JavaScript, browser storage, a mobile bundle, or a downloadable configuration file. |
| Same-origin Frappe page | Frappe session cookie and CSRF token | Send the current CSRF token with state-changing requests. |
| Apex worker or driver portal | Apex personal-token flow | Treat this as a private portal contract, not a general integration credential. |

Use HTTPS for every authenticated request. CORS controls which browser origins
may call a site; it does not protect a leaked credential.

## Server-to-server token authentication

Create a dedicated integration User and grant only the roles and records the
service needs. Generate its API key and secret under **API Access**, then send:

```http
Authorization: token <api_key>:<api_secret>
```

Store the secret in a server-side secret manager. Do not print it in logs,
include it in issue reports, or reuse a personal administrator account.

Example from a confidential server:

```bash
curl --get \
  'https://example.com/api/resource/Transport%20Request' \
  --data-urlencode 'fields=["name","status"]' \
  -H 'Authorization: token <api_key>:<api_secret>' \
  -H 'Accept: application/json'
```

## Browser and mobile clients

Public clients cannot keep an API secret. Use one of these patterns:

1. Register a native Frappe **OAuth Client** and use authorization code with
   PKCE.
2. Send browser requests to a backend-for-frontend that holds the Frappe
   credential and exposes only the operations the browser needs.
3. Serve the page from the Frappe site and use its session and CSRF lifecycle.

Do not place an API key and secret in a browser `fetch` example, environment
variable shipped with a frontend bundle, local storage, or a service worker.

## CORS

For a cross-origin browser client, set the allowed origin in the site's
`site_config.json`:

```json
{
  "allow_cors": "https://portal.example.com"
}
```

Use an explicit list when more than one origin is required:

```json
{
  "allow_cors": [
    "https://portal.example.com",
    "http://localhost:3000"
  ]
}
```

**Apex Integration Settings** records intended origins but does not change
`site_config.json`. The server administrator must apply and review the actual
configuration.

## API choices

### Generic Frappe REST

Frappe exposes permitted DocTypes through:

```text
GET    /api/resource/<DocType>
GET    /api/resource/<DocType>/<name>
POST   /api/resource/<DocType>
PUT    /api/resource/<DocType>/<name>
DELETE /api/resource/<DocType>/<name>
```

Frappe evaluates the authenticated user's document permissions. Additional row
scope is not universal: it depends on the DocType, permission query hooks, and
controller involved. Test every required read and write using the exact
integration user. The [permissions reference](../reference/permissions.md)
documents Apex role and row-scope rules.

### Whitelisted methods

Call an approved method through:

```text
/api/method/<dotted.python.path>
```

Use purpose-built methods when an operation spans records, applies a workflow,
or needs domain validation. A portal page gate does not authorize its API;
every method must enforce its own permissions and scope.

The [route reference](../reference/routes-workspaces.md#served-portal-routes)
lists first-party route audiences and controllers. It is not a promise that
every portal method is a public third-party contract.

### Workflow actions

Advance workflow-controlled records with Frappe's workflow action instead of
writing a status field directly:

```text
POST /api/method/frappe.model.workflow.apply_workflow
```

The authenticated user still needs the required transition role and document
access.

## Integration checklist

1. Create a dedicated least-privilege User or OAuth Client.
2. Confirm read, create, update, submit, and cancel access separately.
3. Confirm Project, Building, Company, Employee, or ownership scope with real
   test data.
4. Configure HTTPS and explicit CORS origins.
5. Redact credentials and personal data from logs.
6. Handle `401`, `403`, `409`, `417`, `429`, and `5xx` responses without retry
   loops that duplicate transactions.
7. Record the Apex version and endpoint when reporting a reproducible issue.

Report integration defects at
[github.com/iabodysa/apex/issues](https://github.com/iabodysa/apex/issues).
