# Copyright (c) 2026, afmcoltd
"""Public Vehicle Incident web form.

A Guest submission is saved by Frappe's own Web Form ``accept`` (frappe/website/
doctype/web_form/web_form.py:598-663): it reads this Web Form's declared field
list, builds the document from the POST body, and calls ``Document.insert()``
directly — there is no separate endpoint here for it to reach instead. The
guest-intake guards (the honeypot, the free-text length caps, and the reset of
every disposition/recovery field on a new guest-authored record) live on
``VehicleIncident._guard_public_intake`` (apex/salis/doctype/vehicle_incident/
vehicle_incident.py), which runs from ``validate()`` on every insert regardless
of which caller reached it.
"""


def get_context(context):
    """Disables page caching for the Vehicle Incident web form."""
    context.no_cache = 1
