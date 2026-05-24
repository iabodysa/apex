# Security Policy

## Supported Versions

Only the latest version of Apex Habitat on the `apex` branch receives security fixes.

## Reporting a Vulnerability

Email security reports to: afm@afmcoltd.com

Do not open public GitHub issues for security vulnerabilities.

## QR Web Form Attack Surface

The Accommodation Resident Request web form is publicly accessible without authentication.
Any person with the QR code URL can submit a request.

Known mitigations in place:
- IP-based rate limiting: 5 submissions per IP per 60 seconds
- Honeypot field: rejects automated bot submissions
- No PII collection beyond an optional contact number
- Anonymous tracking codes generated server-side (not guessable)

Known residual risks:
- Distributed submissions from multiple IPs cannot be rate-limited at application layer
- No CAPTCHA (by design — QR scan context makes CAPTCHA UX hostile)
- Location tokens are not secret (anyone with the QR can use the token)

## `ignore_permissions=True` Inventory

Server-side code uses `ignore_permissions=True` in scheduler and background tasks where no user session is present. These are documented in `docs/adr/controller-patterns.md`.
