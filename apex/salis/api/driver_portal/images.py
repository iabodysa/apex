# Copyright (c) 2026, afmcoltd
"""Image payload validation for the token-scoped portal write endpoints.

``verified_image_type`` proves a base64 data URI carries the image type it declares
and returns that type. A calling endpoint keeps its own filename policy and size
ceiling; this module states only what the bytes have to prove.
"""

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


def _invalid_photo(message):
    """Raises a validation error carrying the given message for a rejected photo."""
    frappe.throw(message, frappe.ValidationError)


def _has_exact_container_end(decoded, image_format):
    """Reject bytes appended after an otherwise valid image container."""
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
    """Prove a base64 data URI really carries the image it declares, and name it.

    Returns the verified content type. Refuses anything the BYTES do not support:
    a declared type outside the accepted set, a payload that is not exact base64, a
    size or dimension past the ceiling, a container PIL cannot open or whose format
    disagrees with the declaration, and trailing bytes after a valid container.
    ``expected_type`` pins the answer to one type when the caller already knows it
    (the driver door derives it from the filename); left None, the declaration in
    the URI is what gets verified — which is why a renamed non-image cannot pass.
    ``max_bytes`` lets a door keep its own published size ceiling.
    """
    if not isinstance(photo, str):
        _invalid_photo(_("The photo data is invalid."))
    max_bytes = max_bytes or MAX_IMAGE_BYTES

    match = _DATA_URI.fullmatch(photo)
    if not match or (expected_type and match.group(1) != expected_type):
        _invalid_photo(_("The photo data is invalid."))
    content_type = match.group(1)
    encoded = match.group(2)
    if len(encoded) > ((max_bytes + 2) // 3) * 4:
        _invalid_photo(_("The photo is too large."))
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        _invalid_photo(_("The photo data is invalid."))
    if not decoded or base64.b64encode(decoded).decode("ascii") != encoded:
        _invalid_photo(_("The photo data is invalid."))
    if len(decoded) > max_bytes:
        _invalid_photo(_("The photo is too large."))

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
                    _invalid_photo(_("The photo dimensions are too large."))
                image.verify()
    except (
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
    ):
        _invalid_photo(_("The photo data is invalid."))
    if (
        image_format != _PIL_FORMATS[content_type]
        or not _has_exact_container_end(decoded, image_format)
    ):
        _invalid_photo(_("The photo data is invalid."))

    return content_type
