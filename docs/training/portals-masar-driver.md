# 10. Portals — Driver & Worker (Masar)

[← Back to index](README.md)

Apex ships two mobile, self-service web portals. Both are **English** (staff are
multinational) and **identity-scoped** — a user only ever sees their own records.

---

## Driver Portal — `/driver`

A logged-in, identity-scoped mobile web app. Each driver only ever sees and acts
on **their own** records — the client never supplies a driver id; the server
resolves it from the signed-in user's linked **Salis Driver** record.

### What a driver can do

| Action | Behaviour |
|--------|-----------|
| **View profile** | Read their own Salis Driver record |
| **View my vehicle** | Read the vehicle currently bound to them |
| **Today's trips** | Read today's Dispatch Trips assigned to them |
| **My route** | Read today's worker-route stops assigned to them |
| **Check in / Check out** | Record and submit today's **Driver Attendance**, optionally with a photo |
| **Submit fuel request** | Raise a **Fuel Request** for their bound vehicle |
| **Raise support ticket** | File a **Support Ticket** (category, priority, subject, description) |
| **My tickets** | Read their own support tickets |

### Permissions
Drivers hold only **Read** (and narrow **Create**) desk permissions — Driver
Attendance (read/create/submit), Support Ticket (read/create), Salis
Driver/Vehicle (read). They cannot browse other drivers' data. The portal is the
intended surface; the desk is not.

### Notes for trainers
- The portal requires login; guests are redirected to the sign-in page.
- A driver user must be **linked to a Salis Driver record** (and that driver to a
  vehicle) for vehicle/fuel actions to resolve. Unlinked staff see navigation
  hints to the desk instead.
- Appearance follows the **Salis Portal Theme** (AFMCO / Frappe / Dark); no
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
- Appearance reuses the **Salis Portal Theme** (theme + optional brand overrides).

_[screenshot: Masar worker home — profile, accommodation, transport]_

> **Security note:** because Masar is guest-accessible by token, the link itself
> is the credential. Issue tokens through the Masar Worker Token record and
> re-issue (rotate) if a link is exposed.
