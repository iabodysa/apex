# Copyright (c) 2026, afmcoltd
"""Trip Boarding State — child row of Dispatch Trip.

One row per manifest worker, tracking the boarding/departure flow: whether they
have boarded, how many "remaining passengers" notifications the driver has sent
(notify_count + notify_at), and how many "please wait" requests the worker has
made back (wait_count + wait_at). Populated from the trip's manifest when the
trip starts (the first scan/self-confirm). Caps and grace come from Salis
Settings; the controller is thin — the flow logic lives in salis/api/boarding_flow.py.
"""

from __future__ import annotations

from frappe.model.document import Document


class TripBoardingState(Document):
    pass
