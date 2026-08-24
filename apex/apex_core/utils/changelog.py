# Copyright (c) 2026, afmcoltd

import os
import re

import frappe
from frappe.utils import get_datetime

_NOTE_NAME = re.compile(r"^v(\d+)_(\d+)_(\d+)\.md$")
_RELEASED_AT = re.compile(r"<!--\s*released:\s*([^>]+?)\s*-->")
_LINK = re.compile(r"<!--\s*link:\s*([^>]+?)\s*-->")
_DEFAULT_LINK = "/app"


def _subtitle(body):
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "<!--", "-", "*")):
            continue
        return stripped
    return ""


def _release_from_note(path, version):
    body = frappe.read_file(path) or ""
    released = _RELEASED_AT.search(body)
    if not released:
        return None
    subtitle = _subtitle(body)
    return {
        "title": f"Apex {version} — {subtitle}" if subtitle else f"Apex {version}",
        "app_name": "apex",
        "link": (_LINK.search(body).group(1) if _LINK.search(body) else _DEFAULT_LINK),
        "creation": released.group(1),
    }


def shipped_releases():
    folder = os.path.join(frappe.get_app_path("apex"), "change_log")
    found = []
    for series in sorted(os.listdir(folder)):
        series_path = os.path.join(folder, series)
        if not os.path.isdir(series_path):
            continue
        for name in sorted(os.listdir(series_path)):
            match = _NOTE_NAME.match(name)
            if not match:
                continue
            numbers = tuple(int(part) for part in match.groups())
            release = _release_from_note(os.path.join(series_path, name), ".".join(str(n) for n in numbers))
            if release:
                found.append((numbers, release))
    found.sort(key=lambda item: item[0], reverse=True)
    return [release for _, release in found]


_FEED_TITLE_MAX = 140

_FEED_MAX = 20


def _clip_title(title):
    title = title.strip()
    if len(title) <= _FEED_TITLE_MAX:
        return title
    return title[: _FEED_TITLE_MAX - 1].rstrip() + "…"


def get_changelog_feed(since):
    since_dt = get_datetime(since)
    items = [
        {**r, "title": _clip_title(r["title"])}
        for r in shipped_releases()
        if get_datetime(r["creation"]) > since_dt
    ]
    return items[:_FEED_MAX]
