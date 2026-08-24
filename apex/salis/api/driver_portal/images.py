# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import base64
import binascii
import re
import warnings
from io import BytesIO

import frappe
from frappe import _
from PIL import Image, UnidentifiedImageError


MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_WIDTH = 8192
MAX_IMAGE_HEIGHT = 8192
MAX_IMAGE_PIXELS = 20_000_000
_DATA_URI = re.compile(
    r"^data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/]+={0,2})$"
)
_PIL_FORMATS = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}


def _has_exact_container_end(decoded, image_format):
    if image_format == "PNG":
        return decoded.endswith(b"\x00\x00\x00\x00IEND\xaeB\x60\x82")
    if image_format == "JPEG":
        return decoded.endswith(b"\xff\xd9")
    if image_format == "WEBP":
        return (
            len(decoded) >= 12
            and decoded[:4] == b"RIFF"
            and decoded[8:12] == b"WEBP"
            and int.from_bytes(decoded[4:8], "little") + 8 == len(decoded)
        )
    return False


def verified_image_type(photo, expected_type=None, max_bytes=None):
    if not isinstance(photo, str):
        frappe.throw(_("The photo data is invalid."), frappe.ValidationError)
    max_bytes = max_bytes or MAX_IMAGE_BYTES

    match = _DATA_URI.fullmatch(photo)
    if not match or (expected_type and match.group(1) != expected_type):
        frappe.throw(_("The photo data is invalid."), frappe.ValidationError)
    content_type = match.group(1)
    encoded = match.group(2)
    if len(encoded) > ((max_bytes + 2) // 3) * 4:
        frappe.throw(_("The photo is too large."), frappe.ValidationError)
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        frappe.throw(_("The photo data is invalid."), frappe.ValidationError)
    if not decoded or base64.b64encode(decoded).decode("ascii") != encoded:
        frappe.throw(_("The photo data is invalid."), frappe.ValidationError)
    if len(decoded) > max_bytes:
        frappe.throw(_("The photo is too large."), frappe.ValidationError)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(decoded)) as image:
                image_format = image.format
                width, height = image.size
                if (
                    width <= 0
                    or height <= 0
                    or width > MAX_IMAGE_WIDTH
                    or height > MAX_IMAGE_HEIGHT
                    or width * height > MAX_IMAGE_PIXELS
                ):
                    frappe.throw(_("The photo dimensions are too large."), frappe.ValidationError)
                image.verify()
    except (
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
    ):
        frappe.throw(_("The photo data is invalid."), frappe.ValidationError)
    if (
        image_format != _PIL_FORMATS[content_type]
        or not _has_exact_container_end(decoded, image_format)
    ):
        frappe.throw(_("The photo data is invalid."), frappe.ValidationError)

    return content_type
