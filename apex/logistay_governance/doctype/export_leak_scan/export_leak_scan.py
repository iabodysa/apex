# Copyright (c) 2026, AFMCO and contributors
"""Export Leak Scan controller.

Records one privacy scan at the export boundary. owner_internal is informational
and always passes; every other audience is fail-closed: unless the verdict is an
explicit ``pass`` the record is normalised to ``blocked`` so an unscanned or
unsupported artifact can never read as clean. The HOLD that stops the export is
raised by the shared ``gate_export`` service; this controller only keeps the
recorded verdict honest.
"""

from __future__ import annotations

from frappe.model.document import Document


class ExportLeakScan(Document):
    def validate(self) -> None:
        if self.gov_audience == "owner_internal":
            # Internal audience is never blocked; default a missing verdict to pass.
            if not self.gov_verdict:
                self.gov_verdict = "pass"
            return
        # Third-audience export: only an explicit pass is clean; everything else
        # (blank verdict, unscanned format, scanner unavailable) is fail-closed.
        if self.gov_verdict != "pass":
            self.gov_verdict = "blocked"
