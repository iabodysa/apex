# Copyright (c) 2026, AFMCO and contributors
"""Private image attachments accepted by driver-token write endpoints."""

from __future__ import annotations

import base64
import binascii
import os
import re
import warnings
from io import BytesIO

import frappe
from frappe import _
from frappe.utils.file_manager import save_file
from PIL import Image, UnidentifiedImageError


MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_WIDTH = 8192
MAX_IMAGE_HEIGHT = 8192
MAX_IMAGE_PIXELS = 20_000_000
_IMAGE_TYPES = {
	".jpg": "image/jpeg",
	".jpeg": "image/jpeg",
	".png": "image/png",
	".webp": "image/webp",
}
_DATA_URI = re.compile(
	r"^data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/]+={0,2})$"
)
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,127}$")
_PIL_FORMATS = {
	"image/jpeg": "JPEG",
	"image/png": "PNG",
	"image/webp": "WEBP",
}


def _invalid_photo(message):
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


def save_driver_image(photo, filename, doctype, name):
	"""Validate and save one private native File on an authorized new record."""
	if not photo and not filename:
		return None
	if not isinstance(photo, str) or not isinstance(filename, str):
		_invalid_photo(_("A photo and filename are required together."))

	if (
		not filename
		or filename != filename.strip()
		or filename.startswith(".")
		or filename != os.path.basename(filename)
		or "/" in filename
		or "\\" in filename
		or any(ord(character) < 32 or ord(character) == 127 for character in filename)
		or not _SAFE_FILENAME.fullmatch(filename)
	):
		_invalid_photo(_("The photo filename is invalid."))
	extension = os.path.splitext(filename)[1].lower()
	expected_type = _IMAGE_TYPES.get(extension)
	if not expected_type:
		_invalid_photo(_("The photo must be a JPEG, PNG, or WebP image."))

	match = _DATA_URI.fullmatch(photo)
	if not match or match.group(1) != expected_type:
		_invalid_photo(_("The photo data is invalid."))
	encoded = match.group(2)
	if len(encoded) > ((MAX_IMAGE_BYTES + 2) // 3) * 4:
		_invalid_photo(_("The photo is too large."))
	try:
		decoded = base64.b64decode(encoded, validate=True)
	except (binascii.Error, ValueError):
		_invalid_photo(_("The photo data is invalid."))
	if not decoded or base64.b64encode(decoded).decode("ascii") != encoded:
		_invalid_photo(_("The photo data is invalid."))
	if len(decoded) > MAX_IMAGE_BYTES:
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
		image_format != _PIL_FORMATS[expected_type]
		or not _has_exact_container_end(decoded, image_format)
	):
		_invalid_photo(_("The photo data is invalid."))

	return save_file(
		filename,
		photo,
		doctype,
		name,
		decode=True,
		is_private=1,
	)
