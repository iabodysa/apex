# 10. Portals — Driver & Worker (Masar)

[← Back to index](README.md)

Apex serves **seven** portal routes from six built bundles. Two of them are the
mobile, self-service apps this page covers — `/driver` and `/masar` — reached by a
personal link rather than a login. The other five are session- and role-gated
operator surfaces: `/fleet` (employee self-service), `/fleet-os` (fleet supervisor
board), `/housing`, `/safety`, and `/masar-supervisor` (route supervisor). Every
route, its audience, and its authentication path are listed once in
[Served portal routes](../../README.md#served-portal-routes).

Both self-service apps are **multilingual** and **identity-scoped** — a worker or
driver only ever sees their own records. Masar ships English, Arabic, Urdu, Hindi,
and Bengali; the Driver portal ships English and Arabic. Each has an in-app
language switcher, and Arabic and Urdu render right-to-left.

---

## Driver Portal — `/driver`

An identity-scoped mobile web app opened through a personal driver link. Each
driver only ever sees and acts on **their own** records — the client never
supplies a driver id; the server resolves it from the link credential.

### What a driver can do

| Action | Behaviour |
|--------|-----------|
| **View profile** | Read their own Salis Driver record |
| **View my vehicle** | Read the vehicle currently bound to them |
| **Today's trips** | Read today's Dispatch Trips assigned to them |
| **My route** | Read today's worker-route stops assigned to them |
| **Check in / Check out** | Record and submit today's **Driver Attendance**, optionally with a photo |
| **Submit fuel request** | Raise a **Fuel Request** for their bound vehicle |
| **Raise support ticket** | File a native **Issue** (category, priority, subject, description) |
| **My tickets** | Read their own **Issues** |
| **Exit clearance** | View their own clearance state and request a short-lived certificate download link after clearance is issued |

### Permissions
Drivers do not sign in to the desk. The **Driver** role is provisioned with
`desk_access = 0`, so the role opens no desk at all, and the barcode cutover
disables the legacy driver Website User account once that driver has a live token
(`apex/patches/v2_0/disable_driver_login_users_barcode_cutover.py`; accounts that
hold an elevated operational role are left enabled, and no account is ever
deleted). Identity is the personal link token, resolved server-side on every call.

The role still carries a minimal, **owner-only** document permission set, so a
driver can never read another driver's rows even through the API. Every one of its
rows carries `if_owner`:

Those five are the whole grant. **Salis Vehicle** is not among them — the portal
reads the bound vehicle on the driver's behalf after resolving the token.

Field support tickets are native ERPNext **Issue** records (the old "Support
Ticket" DocType was retired). The Driver role holds **no** Issue permission at
all: the portal creates and reads the ticket on the driver's behalf, tagging it
with a `custom_driver` link and refusing to return any Issue whose `custom_driver`
is not the resolved driver. The portal is the only surface; the desk is not.

### Notes for trainers
- The personal driver link is the credential. Do not share it; reissue it if it
  is exposed.
- The driver must be linked to a vehicle for vehicle and fuel actions to resolve.
- Clearance status is read-only in the portal. The certificate key is generated
  only when the driver taps the download action and expires automatically.
- Appearance follows the **Driver Portal Theme** (AFMCO / Frappe / Dark); no
  configuration is needed for it to render with safe defaults.

_[screenshot: Driver Portal home — check-in, my vehicle, today's trips]_
_[screenshot: Driver Portal — submit fuel request]_

---

## Worker Portal (Masar) — `/masar`

A worker self-service app for **housed and transported employees**. Workers are
**not Frappe users** — identity is an unguessable personal **token**, resolved
server-side, scoping every query to one Employee.

### How access works
- A worker opens their **personal link** `/masar?w=<token>` on a phone.
- The page is **guest-accessible by design** (no login redirect): the token, not a
  login, identifies the worker.
- Every worker endpoint scopes its query to that one Employee — a worker can only
  ever see their own profile, accommodation, transport, and requests.

### What a worker can do
- **Profile** — view their own employee profile.
- **Accommodation** — see their current housing assignment.
- **Transport** — see their transport/route information.
- **Requests** — raise and track self-service requests.

### Notes for trainers
- The token link is **personal and unguessable** — treat it like a password; do
  not share or post it.
- Tokens are managed via the **Masar Worker Token** record (Apex Core).
- Appearance reuses the **Driver Portal Theme** (theme + optional brand overrides).

_[screenshot: Masar worker home — profile, accommodation, transport]_

> **Security note:** because Masar is guest-accessible by token, the link itself
> is the credential. Issue tokens through the Masar Worker Token record and
> re-issue (rotate) if a link is exposed.
