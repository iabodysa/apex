# Copyright (c) 2026, afmcoltd
"""The in-app release feed, read from the notes that ship with the release.

The notes under ``change_log/`` are the only source: a release is described once, and
adding one means adding its file. Nothing here restates a release, because a second copy
falls behind silently — nothing fails when it is forgotten.

Each note carries two machine-readable lines that a reader never sees, because markdown
hides an HTML comment: ``<!-- released: YYYY-MM-DD HH:MM:SS -->`` (the moment the feed
reports, so the bell's "since you last looked" filter keeps working across a clone, where
a file's own mtime is only its checkout time), and an optional ``<!-- link: /driver -->``
for a release whose feed item should open somewhere other than the desk.
"""

import os
import re

import frappe
from frappe.utils import get_datetime

_NOTE_NAME = re.compile(r"^v(\d+)_(\d+)_(\d+)\.md$")
_RELEASED_AT = re.compile(r"<!--\s*released:\s*([^>]+?)\s*-->")
_LINK = re.compile(r"<!--\s*link:\s*([^>]+?)\s*-->")
_DEFAULT_LINK = "/app"


def _subtitle(body):
    """The first line of prose under the heading, which is the note's own summary."""
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "<!--", "-", "*")):
            continue
        return stripped
    return ""


def _release_from_note(path, version):
    """Builds a release feed entry from one change-log note's release timestamp, link, and subtitle.

    ``frappe.read_file`` (frappe/__init__.py:1720) returns "" for a missing or
    unreadable path instead of raising, which is why a note that has not been written
    yet drops out of the feed rather than breaking the whole login modal.
    """
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
    """Every release note on disk, newest version first.

    ``frappe.get_app_path`` (frappe/__init__.py:1484) resolves the installed app's own
    directory, so this reads the notes that SHIPPED with the running version rather
    than any path the site happens to be started from. The feed is derived from those
    files and not from a list in code, so a note cannot exist without appearing.
    """
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
    """Truncates a title to the feed's maximum length, appending an ellipsis when it is cut."""
    title = title.strip()
    if len(title) <= _FEED_TITLE_MAX:
        return title
    return title[: _FEED_TITLE_MAX - 1].rstrip() + "…"


def get_changelog_feed(since):
    """
    Returns Apex release items newer than `since`, newest first, capped at
    `_FEED_MAX`. Registered via hooks.py get_changelog_feed hook.
    Frappe's fetch_changelog_feed() calls this and deduplicates by exact field match.
    """
    since_dt = get_datetime(since)
    items = [
        {**r, "title": _clip_title(r["title"])}
        for r in shipped_releases()
        if get_datetime(r["creation"]) > since_dt
    ]
    return items[:_FEED_MAX]
