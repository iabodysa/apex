# Copyright (c) 2026, afmcoltd
"""The Issue Type and Issue Priority records this app ships, named in one place.

These names are read by three consumers that must agree or the support desk breaks in
a way nothing reports: the ``fixtures`` hook that selects the rows to ship, the SLA
contract that hangs response and resolution times off a priority, and the refusals that
stop an operator renaming or deleting a shipped row. A name present in one list and
absent from another produces an SLA pointing at a row nobody recreates, or a refusal
that guards nothing.

The module imports nothing, because ``apex/hooks.py`` reads it while frappe is still
booting; anything importing frappe here would be loaded before the framework is ready.
Kept beside ``workflow_names`` for the same reason and in the same shape.
"""

ISSUE_TYPES = ("Vehicle", "Fuel", "Attendance", "Salary", "Complaint", "Other")
ISSUE_PRIORITIES = ("Low", "Medium", "High", "Urgent")
