# Portal identity — QR enrolment, device sessions, and an audit trail

Status: proposed. Supersedes nothing until A-521.1 is decided.

## The problem this solves

A worker or driver reaches the portal today by holding a link. `Masar Worker Token` stores the
credential hashed (`token`, permlevel 1) and Fernet-encrypted (`token_enc`, permlevel 1), expires it
after `TOKEN_TTL_DAYS = 180`, and refuses a disabled-to-enabled transition without server-side
rotation. What it does not do is tie the credential to a device or limit how many holders may use it
at once, so a link that escapes — forwarded, screenshotted, left on a borrowed handset — grants the
subject's full portal scope, silently, for up to six months.

The current row carries no device identity at all. Its fields are `holder_type`, `party_type`,
`party`, `employee`, `driver`, `enabled`, `token`, `token_enc`, `expires_on`, `last_generated_on`,
`last_generated_by`. Who issued it and when are recorded; which device used it is not recorded
anywhere.

## The shape

```
QR code            issued by the supervisor, consumed ONCE
   │                 on scan: enable the Website User, open a session, register the device
   ▼
Portal session     what the device carries afterwards
                     bounded by simultaneous_sessions, revocable per device
```

A leaked QR is dead the moment it is used, because it is an enrolment key rather than an access
credential. A leaked session cookie is device-local and already appears in the audit trail.

## What the framework provides, and where

Four of the five moving parts are native primitives, not new code.

| Concern | Primitive | Source |
| --- | --- | --- |
| Holder identity without a desk seat | `User.user_type = "Website User"` | `frappe/core/doctype/user/user.py:314` |
| Worker vs driver as a declared kind | `User Type` DocType — `apply_user_permission_on`, `user_id_field`, auto-role, auto User Permission | `frappe/core/doctype/user_type/user_type.py:26,32,249-268` |
| Devices per holder | `User.simultaneous_sessions`, read at login, oldest session evicted | `frappe/sessions.py:66-79` |
| Access audit | `Activity Log` — `operation`, `status`, `user`, `ip_address`, `reference_doctype`, `reference_name` | `frappe/core/doctype/activity_log/activity_log.json` |

`Access Log` is the wrong shelf and is named here so nobody reaches for it: its fields are
`export_from`, `file_type`, `report_name`, `page` — it records exports, prints and report views, not
authentication.

Two things are deliberately NOT taken from the framework:

**`api_key` / `api_secret` are rejected as the device credential.** `generate_keys` writes a single
`api_secret` onto the User row (`frappe/core/doctype/user/user.py:1358`), so rotating one device's
credential logs out every device that holder owns. It is also a bearer with no expiry, which is the
property this design exists to remove. The per-device credential is the session.

**`generate_keys` is gated `frappe.only_for("System Manager")`** at `user.py:1350`, so a housing or
fleet supervisor cannot call it. Issuance stays on the existing `authorize_issuance` path, which
already grades role and scope.

## What Apex still has to build

Three pieces, and no more.

### 1. `Portal Device` — one row per enrolled device

A new DocType, one row per device per holder, replacing nothing. Fields:

- `user` (Link User, required) — the holder
- `holder_type` (Select `Worker` / `Driver`) — mirrors the token's own axis so a device is never
  ambiguous about which portal it belongs to
- `device_label` (Data) — what the holder sees in the device list; defaults from the user agent
- `device_hash` (Data, read-only, unique with `user`) — a salted hash of the enrolment fingerprint,
  never the raw fingerprint
- `enrolled_on` (Datetime, read-only), `enrolled_by` (Link User, read-only) — the supervisor who
  issued the QR that created it
- `last_seen_on` (Datetime, read-only)
- `revoked` (Check, read-only) — set by the holder or a supervisor; never cleared, a returning device
  enrols afresh

`enrolled_by` matters as much as `user`: it is the only field that answers "who let this device in"
after the fact.

### 2. One-time enrolment

The QR carries an enrolment key, not the portal credential. On scan, in one transaction:

1. Resolve the key. A consumed, expired or unknown key is refused with the same message and the same
   delay as a wrong key, so the response cannot distinguish them.
2. Enable the holder's `Website User` if it is not already enabled.
3. Create the `Portal Device` row, or match an existing unrevoked one by `device_hash`.
4. Open the session.
5. Mark the key consumed. It is never re-armed; a second device needs a second QR.

The refusal path and the throttle already exist — `_throttle_bad_token_attempt` and the
`rate_limit` decorators on the portal endpoints — and are reused rather than rewritten.

### 3. The device list the holder can act on

A portal screen showing the holder's own devices: label, when it enrolled, when it was last seen,
and a control that revokes one. Revoking sets `revoked` and deletes that device's session through
`frappe.sessions.delete_session`. A holder who cannot see his devices cannot notice a leak, which is
the failure this whole design is aimed at.

## The log — required, not optional

Every enrolment, refusal and revocation is written, and it is written where an auditor will look.

**`Activity Log` is the primary record**, because Frappe already writes every login and logout there
and a portal event that lives somewhere else will be read separately or not at all. Each portal
event writes one entry with:

- `operation` — `Portal Enrolment`, `Portal Refusal`, `Portal Device Revoked`
- `status` — `Success` or `Failed`
- `user` — the holder, or the supervisor for a revocation performed on his behalf
- `ip_address` — taken from the request, not from the client payload
- `reference_doctype` / `reference_name` — `Portal Device` and its row, so the log and the device
  join without a text search

**A refusal is logged as loudly as a success.** A leak shows up as refused attempts before it shows
up as anything else, and a log that only records what worked cannot see it.

**What is never written to the log:** the raw token, the enrolment key, the raw device fingerprint,
or any hash that would let a reader of the log reconstruct one. The log names the device row; the
row holds the salted hash.

A dedicated `Portal Access Log` DocType is deliberately NOT proposed. `Activity Log` already carries
every field the events need, is already retained and pruned by `Log Settings`, and is already where
an administrator looks for a login. A second log would have to be retained, pruned, permissioned and
read separately, and would split the answer to "when did this person get in" across two places.

## What this changes for the existing token

`Masar Worker Token` does not disappear on day one. The enrolment key can be minted from the same
row and the same issuance path, so the supervisor's screen and its permissions are unchanged. The
token stops being a standing credential and becomes a one-shot enrolment key; `expires_on` then
governs how long an unscanned QR stays valid, and 180 days is too long for that role — the enrolment
window should be days, not months, and that number is a decision this spec leaves open.

## Open decisions

1. Whether every worker becomes a `Website User` at all — A-521.1, the gate on everything above.
2. The enrolment-key window, once the token is no longer a standing credential.
3. `simultaneous_sessions` per holder type: a driver plausibly needs one device, a worker may share
   a handset. The field is per-user, so the default belongs on the `User Type`.
4. Whether a supervisor may revoke another holder's device from the desk, or only re-issue.

## What proves it works

- A consumed enrolment key is refused on a second scan, from any device, and the refusal is in
  `Activity Log` with `status = Failed`.
- Enrolling a device beyond `simultaneous_sessions` evicts the oldest session and leaves both device
  rows visible to the holder.
- A revoked device's session is gone from `tabSessions` in the same transaction as the revocation.
- The holder's device list shows only his own rows, under `User Permission` from the `User Type`,
  with no `ignore_permissions` anywhere on the path.
- No log entry, anywhere, contains a raw token, a raw enrolment key or a raw fingerprint.
