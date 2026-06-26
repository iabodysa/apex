"""Trip Stop Progress — child row of Trip Start Log.

One row per route stop the driver works through: its sequence, name, the source
Route Stop row name (stable identity across reloads), and whether it has been
marked done (with the timestamp). Lets a started trip persist per-stop completion
server-side so it survives a refresh. The controller is intentionally thin — the
write path lives on the driver-portal API.
"""

from __future__ import annotations

from frappe.model.document import Document


class TripStopProgress(Document):
    pass
