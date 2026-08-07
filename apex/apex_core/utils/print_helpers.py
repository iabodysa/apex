# Copyright (c) 2026, afmcoltd
import frappe

from apex.apex_core.doctype.masar_worker_token.masar_worker_token import masar_qr_data_uri


def doc_verify_qr(doctype: str, name: str):
    """QR data-URI pointing at the document's own desk record, for print verification.

    A printed page leaves the system; the QR is how a reader holding the paper gets
    back to the record that issued it. Returns None when the QR library is absent,
    which the templates render as no QR rather than a broken image.
    """
    if not (doctype and name):
        return None
    return masar_qr_data_uri(frappe.utils.get_url(f"/app/{frappe.scrub(doctype).replace('_', '-')}/{name}"))
