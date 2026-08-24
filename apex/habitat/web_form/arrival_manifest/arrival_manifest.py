# Copyright (c) 2026, afmcoltd
"""Public Arrival Manifest web form.

A Guest submission is saved by Frappe's own Web Form ``accept`` (frappe/website/
doctype/web_form/web_form.py:598-663): it reads this Web Form's declared field
list, builds the document from the POST body, and calls ``Document.insert()``
directly — there is no separate endpoint here for it to reach instead. The
guest-intake guards live on ``ArrivalBatch.validate`` (apex/habitat/doctype/
arrival_batch/arrival_batch.py), which runs on every insert regardless of which
caller reached it: the honeypot, the 500-row cap, and the clearing of each
worker row's read-only "Arrived As" link on a Guest submission.
"""


def get_context(context):
    """Disables caching for the public Arrival Manifest web form page."""
    context.no_cache = 1
