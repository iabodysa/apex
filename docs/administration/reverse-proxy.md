# Deployment Prerequisite: the reverse proxy must overwrite `X-Forwarded-For`

Any reverse proxy, load balancer or CDN placed in front of this application must
**overwrite** the `X-Forwarded-For` request header with the address of the peer it
is talking to. It must not **append** the caller's own value to it.

This is a deployment requirement. No setting inside the application can satisfy
it, and none can detect a violation on its own — so this page states the
requirement and gives you a command that grades your running deployment against
it.

If you serve the application with no proxy in front of it at all, the requirement
does not apply, but read [Section 5](#5-reading-the-verdict) anyway: the check
grades that case too, and it is not automatically safe.

Source line references below were read against Frappe `15.109.0`.

---

## 1. Why it matters

Frappe fills `frappe.local.request_ip` from the **first** `X-Forwarded-For` entry,
and asks nothing about who wrote it:

```python
def set_request_ip(self):
    if frappe.get_request_header("X-Forwarded-For"):
        frappe.local.request_ip = (frappe.get_request_header("X-Forwarded-For").split(",", 1)[0]).strip()
    elif frappe.get_request_header("REMOTE_ADDR"):
        frappe.local.request_ip = frappe.get_request_header("REMOTE_ADDR")
    ...
```

`frappe/auth.py:64-75`. There is no trusted-proxy list to configure — Frappe
15.109.0 carries no such setting anywhere.

That value is the bucket key for every per-address limit the application applies:
portal bad-token throttling, the boarding scan limiter, and Frappe's own
`@rate_limit(ip_based=True)`. So on a deployment whose edge appends, a caller
that sends a fresh `X-Forwarded-For` value on each request lands in a fresh
window every time and walks straight through all of them — and can equally pin
the blame for a flood on any address it chooses to name.

An **appending** proxy adds its peer to the *end* of whatever the caller sent, so
the caller's claim arrives in front:

```text
client sends:   X-Forwarded-For: 10.0.0.99          (a value the client made up)
proxy appends:  X-Forwarded-For: 10.0.0.99, 10.0.0.7
Frappe reads:   10.0.0.99                           <- the client's own claim
```

An **overwriting** proxy discards the claim and states the peer it actually has:

```text
client sends:   X-Forwarded-For: 10.0.0.99
proxy replaces: X-Forwarded-For: 10.0.0.7
Frappe reads:   10.0.0.7                            <- the real peer
```

Frappe's `ProxyFix` does not close this. It is bound to `serve()` — the
development server — behind an opt-in flag (`frappe/app.py:499-500`), so no
production WSGI path receives it; and even where it does run it rewrites
`request.remote_addr`, which `set_request_ip` never reaches because it reads the
raw header first.

---

## 2. Configuring the edge

Only the **outermost** hop — the one that terminates the caller's connection —
can tell a real peer from a forged claim. That hop must set the header from the
connection it has, not from what arrived in it.

nginx, at the outermost hop:

```nginx
proxy_set_header X-Forwarded-For $remote_addr;
```

`$remote_addr` is the peer of the connection nginx accepted, so this **replaces**
the header. The widely copied `$proxy_add_x_forwarded_for` form is the appending
one: it expands to the incoming header value with `$remote_addr` added to the
end, which is precisely the shape shown above. It is the right choice for an
*inner* hop that sits behind a trusted edge, and the wrong choice for the edge
itself.

Other proxies spell the same choice differently — HAProxy separates
`http-request set-header` from `add-header`; Apache, Caddy, Traefik and managed
cloud load balancers each expose their own forwarded-header option, and several
append by default. Whatever the product, the requirement is the same: at the
outermost hop the caller's value is **discarded and replaced**, never carried
forward. Find which of the product's two forms replaces, and use that one.

Inner hops appending behind a replacing edge are safe, because every appending
hop adds to the tail while a caller's claim can only ever sit at the head. What
must never happen is an appending hop **in front of** the replacing one.

---

## 3. Verifying it

The application ships a read-only check that grades one live request:

```text
apex.apex_core.utils.request_ip_trust.check_request_ip_trust
```

It is whitelisted and restricted to **System Manager**, because its reply names
the address the server believes the caller has.

Call it through the deployment you want to grade — from outside the edge, over
the public address, so the request travels the path a real caller's would — while
planting a documentation-range address in `X-Forwarded-For`:

```bash
curl -s --cookie sid=<system-manager-session-id> \
     -H 'X-Forwarded-For: 192.0.2.7' \
     'https://<your-site>/api/method/apex.apex_core.utils.request_ip_trust.check_request_ip_trust?probe_planted=1'
```

Two things travel in that one command, and both are required.

- **The probe**, in the header. `192.0.2.7` is reserved for documentation
  (RFC 5737; RFC 3849 reserves `2001:db8::/32` for IPv6), so no real client ever
  legitimately carries one. Any address from those ranges works.
- **The assertion**, in the query string. `probe_planted=1` tells the check that
  this same request carried a probe. A query string is forwarded verbatim by a
  proxy, which is why the news arrives that way.

The assertion is needed because a correctly configured edge **destroys** the
probe. Absence of the probe is the pass signal — so without the assertion, the
server cannot tell "the edge erased my probe" from "no probe was ever sent", and
a passing deployment would grade itself inconclusive for doing exactly the right
thing.

Send the **digit**. `probe_planted=true` and `probe_planted=yes` are both read as
0, which spells the assertion away: the check then answers as though no probe had
been planted — `inconclusive`, or `appended` if more than one entry arrived — and
a correctly configured deployment never reaches a pass.

---

## 4. Keeping the two halves together

The assertion cannot be verified by the server: a header the edge destroyed is
precisely what it cannot see. Nothing distinguishes "I planted a probe and the
edge erased it" from "I set the flag and sent an ordinary request".

A person probing their own deployment cannot be misled by that. An **automated**
check can: if the step that injects the header is ever dropped while the query
flag survives, the check reports a permanent pass. So keep the header and the
flag in one command, and treat any pass as void the moment they are edited apart.

---

## 5. Reading the verdict

The reply is a JSON object. `verdict` is the graded string and `trusted` is the
boolean to key an automated check on; `detail` explains the verdict in prose,
`entries` lists the forwarded entries the app received, and `resolved_ip` is the
address Frappe actually put in `request_ip`.

| `verdict` | `trusted` | Meaning |
| --- | --- | --- |
| `overwritten` | `true` | **Pass.** The probe was sent and no entry carries it, so the edge replaced the header with the real peer. |
| `overwritten-then-appended` | `true` | **Pass.** The probe is gone and later entries remain: the caller-facing hop replaced the header and inner hops appended behind it. Confirm every later entry is a hop you operate. |
| `forgeable` | `false` | **Fail.** The probe survived the edge. The header is trusted verbatim, every per-address limit is bypassable, and any address can be framed for another caller's traffic. |
| `appended` | `false` | **Fail.** More than one entry arrived and no probe was asserted, so nothing shows whether the first entry is the caller's claim or a replacement. Treat it as caller-chosen and re-send with the probe. |
| `no-header` | `false` | **Incomplete, not a pass.** No forwarded header reached the app, so the edge's overwrite behaviour went unmeasured. |
| `inconclusive` | `false` | **Not certified.** One entry and no probe asserted — a shape an overwriting proxy and a directly exposed app both produce — or an entry the check cannot read, or a resolved address that is not the first entry. |

Only `overwritten` and `overwritten-then-appended` certify the deployment.
Everything else is a refusal to certify, `no-header` included.

**`no-header` deserves its own attention.** A planted probe that was destroyed
outright does not make it a pass. If nothing proxies the site, the peer address
is genuine and there is nothing to fix. But if a proxy *is* in front and simply
does not set the header, every client in the world collapses onto that proxy's
own address — and one abuser then trips the per-address ceiling for all of them.

### One blind spot, stated plainly

Some edges strip reserved and documentation ranges from the header as a
half-measure while forwarding an ordinary forged claim untouched. The probe
vanishes in both cases, so this check reads such an edge as correct. The blind
spot follows from choosing a non-routable probe, and a routable one could belong
to a real client — so it cannot be closed by recognising more spellings. If your
edge filters by address range rather than replacing the header outright, treat a
pass here as unproven and confirm the replacement in the proxy configuration
itself.

---

## 6. When to run it

- Before a deployment first serves real traffic.
- After any change to the edge: a new proxy or load balancer, a CDN placed in
  front, a certificate or listener migration, a change to forwarded-header
  options.
- After moving the site to a different address or network path.

A `forgeable` or `appended` verdict means the per-address limits in this
application are not protecting anything today. Fix the edge before treating the
deployment as production-ready.
