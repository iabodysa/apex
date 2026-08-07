# Copyright (c) 2026, AFMCO and contributors
"""The OTP lockout policy, in one place.

Two handover flows ask a recipient for a one-time code — Custody Handover and Facility
Asset Delivery — and each carried its own copy of the same three numbers. A copy is not a
policy: tightening the attempt limit in one flow and not the other leaves the looser one
as the way in, and nothing in either file said the other existed.

The home is neutral on purpose. The helpers these constants govern (``hash_otp``,
``generate_otp``) live in the Custody Handover controller, which is one of the two
consumers, so putting a shared policy there would have named one flow as the owner of a
rule that governs both.
"""

MAX_OTP_ATTEMPTS = 3
LOCKOUT_MINUTES = 5
ELEVATED_ROLE = "Accommodation Manager"
