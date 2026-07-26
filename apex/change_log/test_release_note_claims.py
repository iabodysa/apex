# Copyright (c) 2026, AFMCO and contributors
"""A published release note may not promise a deployment property the code denies.

Two shipped notes told operators something the code does not do, and both were
promises about the ENVIRONMENT a deployment may run in rather than about a
feature a user can see:

  * 2.1.2 said the portals "load fully offline". The supervisor map still draws
    its background tiles from OpenStreetMap by default; what actually shipped was
    a site-configuration override plus graceful degradation when tiles fail. A
    reader planning a disconnected site on that sentence gets a blank map.
  * 2.1.0 said the app "installs and migrates against a single clean baseline".
    A site installed under the previous package name cannot migrate at all until
    an operator-driven identity cutover has run, and no patch can heal it,
    because a site resolves patches under the app name it was installed with.

Both notes now carry a dated correction. This guard is the durable half: it
closes the class rather than the two instances.

THE RULE
    An environment absolute (the vocabulary in ``TRIGGERS``) may not appear in a
    published note unless the note and this register together carry three things:
    a registered entry for that note, a code citation that still resolves, and a
    bounding phrase present in the same note.

WHAT EACH PART BUYS
    Registration makes a new absolute a review event. An unregistered one fails,
    so nobody quietly adds "air-gapped" to a note.

    The citation rots loudly, and this is the part that matters. The claim is
    pinned to a file and to a token inside it: delete the tile override or rename
    the cutover entry point and the note that promised it reds in the same build,
    with nobody having to remember the note exists. A register that merely blessed
    a sentence would go stale the moment the code moved underneath it.

    The bounding phrase is what keeps the promise honest to the READER. An
    absolute is tolerated only where the same note also states the boundary the
    code enforces, and the phrase demanded is the operator-facing name of that
    boundary, so note and source stay in step on it.

    The occurrence count stops a second, unreviewed sentence sheltering behind an
    entry approved for the first.

WHAT THIS GUARD DOES NOT CLAIM
    It cannot decide whether an arbitrary English sentence is true. It forces an
    absolute to be reviewed once, pinned to code, and bounded in place. It does
    not read the prose, and it is not a substitute for doing so.

WHY THE VOCABULARY IS NARROW
    Environment and prerequisite absolutes only: the words that make a reader
    plan a network, a site or an upgrade window and get it wrong. Automation
    words ("automatic", "automatically") are deliberately OUT. Four shipped
    sentences use them for in-app automation, a different failure class, and one
    of those points at a subsystem archived in the very next release. Sweeping
    them in here would force either an unverified back-audit of retired
    subsystems or a set of blessed exceptions, and a guard carrying blessed
    exceptions is a guard on its way to being vestigial. Widening the vocabulary
    is a deliberate act: add the trigger, then register every hit it finds with a
    citation somebody actually checked.

Run standalone:  python3 -m unittest apex.change_log.test_release_note_claims -v
"""

import os
import re
import unittest

CHANGE_LOG_DIR = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(CHANGE_LOG_DIR)
REPO_ROOT = os.path.dirname(APP_ROOT)

# Absolutes about the environment a deployment runs in. Each one, unqualified,
# is enough for a reader to plan a site that then does not work.
TRIGGERS = (
    "offline",
    "air-gapped",
    "air gapped",
    "internet",
    "self-contained",
    "zero-downtime",
    "zero downtime",
    "clean baseline",
    "out of the box",
    "nothing to configure",
    "no configuration",
)

# Whitespace in a trigger matches any run of it, so a line wrap inside "clean
# baseline" cannot smuggle the phrase past the scan.
_TRIGGER_RES = tuple(
    (
        trigger,
        re.compile(
            r"\b" + r"\s+".join(re.escape(word) for word in trigger.split()) + r"\b",
            re.I,
        ),
    )
    for trigger in TRIGGERS
)


class NoteClaim:
    """One published note's licence to use environment absolutes.

    ``triggers`` maps each permitted absolute to the EXACT number of times the
    note may use it. ``evidence`` is (repo-relative path, token) pairs that must
    all still resolve. ``bounds`` are phrases that must appear in the note itself.
    """

    def __init__(self, note, triggers, evidence, bounds, why):
        self.note = note
        self.triggers = triggers
        self.evidence = evidence
        self.bounds = bounds
        self.why = why


REGISTER = (
    NoteClaim(
        note=os.path.join("v2", "v2_1_2.md"),
        triggers={"offline": 2, "internet": 1, "air-gapped": 1},
        evidence=(
            ("apex/www/masar_supervisor.py", "apex_map_tile_url"),
            ("apex/www/masar_supervisor.py", "def map_tile_override("),
            (
                "frontend/route_supervisor/src/components/DriverMap.vue",
                "tile.openstreetmap.org",
            ),
            ("frontend/route_supervisor/src/components/DriverMap.vue", "tilesDown"),
        ),
        bounds=("apex_map_tile_url", "background is unavailable"),
        why=(
            "The shipped bullet claims the portals load fully offline. The map "
            "background is fetched from OpenStreetMap unless a deployment sets the "
            "override, so the note must name the override and must state what the "
            "reader sees when no tile source is reachable."
        ),
    ),
    NoteClaim(
        note=os.path.join("v2", "v2_1_0.md"),
        # Twice: once as the shipped line, once quoted back by the correction.
        triggers={"clean baseline": 2},
        evidence=(
            ("apex/patches/v2_0/app_identity_cutover.py", "def cutover("),
            ("apex/patches/v2_0/app_identity_cutover.py", "IdentityCutoverError"),
            ("apex/patches.txt", "app_identity_cutover"),
        ),
        bounds=('Could not find app "apex_habitat"', "upgrade runbook"),
        why=(
            "The shipped line claims a single clean install-and-migrate baseline. A "
            "site installed under the old package name fails migrate outright and "
            "cannot be healed by a patch, so the note must carry the failure the "
            "reader will actually see and point at the operator-driven upgrade."
        ),
    ),
)


def _note_files():
    """Every published note under change_log: the index plus each version note."""
    found = [os.path.join(CHANGE_LOG_DIR, "README.md")]
    for root, _dirs, names in os.walk(CHANGE_LOG_DIR):
        for name in sorted(names):
            if name.endswith(".md") and name != "README.md":
                found.append(os.path.join(root, name))
    return sorted(path for path in found if os.path.isfile(path))


def _published_notes():
    """Note path (relative to change_log) -> its full text."""
    notes = {}
    for path in _note_files():
        with open(path, encoding="utf-8") as handle:
            notes[os.path.relpath(path, CHANGE_LOG_DIR)] = handle.read()
    return notes


def _repo_text(relative_path):
    """Text of a repo-relative file, or None when it no longer exists."""
    path = os.path.join(REPO_ROOT, relative_path)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def trigger_hits(text):
    """Environment absolutes present in one note, mapped to their occurrence count."""
    return {
        trigger: len(pattern.findall(text))
        for trigger, pattern in _TRIGGER_RES
        if pattern.search(text)
    }


def register_gaps(notes, register):
    """Every disagreement between the published notes and the claim register.

    Symmetric on purpose. A note using an absolute nobody registered fails, and
    so does a register entry whose note has stopped using it: a stale entry is
    pre-approval for a sentence no reviewer has read.
    """
    gaps = []
    by_note = {entry.note: entry for entry in register}
    for name, text in sorted(notes.items()):
        entry = by_note.get(name)
        hits = trigger_hits(text)
        for trigger, count in sorted(hits.items()):
            if entry is None or trigger not in entry.triggers:
                gaps.append(
                    f"{name}: unregistered environment absolute {trigger!r}. A note "
                    "may only promise this once an entry in REGISTER cites the code "
                    "that makes it true and names the boundary the note must state."
                )
            elif entry.triggers[trigger] != count:
                gaps.append(
                    f"{name}: {trigger!r} is used {count} time(s), the register "
                    f"approved {entry.triggers[trigger]}. A new sentence carrying an "
                    "already-approved absolute is still a new claim."
                )
        if entry is None:
            continue
        for trigger in sorted(entry.triggers):
            if trigger not in hits:
                gaps.append(
                    f"{name}: register still licenses {trigger!r} but the note no "
                    "longer uses it. Prune the entry rather than leaving standing "
                    "approval behind."
                )
        for phrase in entry.bounds:
            if phrase not in text:
                gaps.append(
                    f"{name}: bounding phrase {phrase!r} is missing. The absolute is "
                    "allowed only while the note states the boundary alongside it."
                )
    for entry in register:
        if entry.note not in notes:
            gaps.append(f"{entry.note}: registered note is not on disk")
    return gaps


def citation_gaps(register, read=_repo_text):
    """Register citations that no longer resolve against the source tree."""
    gaps = []
    for entry in register:
        for path, token in entry.evidence:
            text = read(path)
            if text is None:
                gaps.append(
                    f"{entry.note}: cites {path}, which no longer exists. The note "
                    "still makes the promise this file was the evidence for."
                )
            elif token not in text:
                gaps.append(
                    f"{entry.note}: {path} no longer contains {token!r}. The shipped "
                    "note still promises what that code used to provide."
                )
    return gaps


class TestReleaseNoteClaims(unittest.TestCase):
    def test_scan_finds_the_published_notes(self):
        # Fail-closed: a broken walk would make every assertion below vacuous.
        notes = _published_notes()
        self.assertIn("README.md", notes)
        self.assertGreaterEqual(
            len(notes), 8, f"note scan found only {sorted(notes)} under {CHANGE_LOG_DIR}"
        )

    def test_every_environment_absolute_is_registered_and_bounded(self):
        gaps = register_gaps(_published_notes(), REGISTER)
        self.assertEqual(gaps, [], "Release-note claim register:\n  " + "\n  ".join(gaps))

    def test_every_citation_still_resolves(self):
        gaps = citation_gaps(REGISTER)
        self.assertEqual(
            gaps, [], "Release-note citation has rotted:\n  " + "\n  ".join(gaps)
        )

    def test_detector_reads_the_vocabulary_it_advertises(self):
        self.assertEqual(trigger_hits("nothing here"), {})
        self.assertEqual(trigger_hits("It runs OFFLINE, fully offline."), {"offline": 2})
        self.assertEqual(trigger_hits("an air-gapped site"), {"air-gapped": 1})
        self.assertEqual(trigger_hits("a single  clean   baseline"), {"clean baseline": 1})
        # Substring hits are not claims: "offliner" is not "offline".
        self.assertEqual(trigger_hits("offliner internetworking"), {})

    def test_a_planted_claim_fails_the_guard(self):
        """Guard-of-the-guard: an unreviewed promise must red, in every shape."""
        planted = "The app is fully self-contained and needs no configuration.\n"
        self.assertTrue(register_gaps({"v2/v9_9_9.md": planted}, REGISTER))
        # Same sentence bolted onto a note that IS registered, which is the way a
        # real one would arrive: an extra bullet under an approved entry.
        notes = _published_notes()
        licensed = REGISTER[0].note
        self.assertFalse(register_gaps(notes, REGISTER), "tree must be clean first")
        notes[licensed] += "\nThe portals run air-gapped with nothing to configure.\n"
        planted_gaps = register_gaps(notes, REGISTER)
        self.assertTrue(planted_gaps, "a planted claim in a licensed note went unseen")
        self.assertTrue(
            any("nothing to configure" in gap for gap in planted_gaps),
            f"the unregistered absolute was not the thing reported: {planted_gaps}",
        )
        self.assertTrue(
            any("air-gapped" in gap and "approved" in gap for gap in planted_gaps),
            f"the extra use of an approved absolute went uncounted: {planted_gaps}",
        )

    def test_a_rotted_citation_fails_the_guard(self):
        """The other half: the code moves, the note does not, the build reds."""
        self.assertFalse(citation_gaps(REGISTER), "tree must be clean first")
        self.assertTrue(citation_gaps(REGISTER, read=lambda _path: None))
        self.assertTrue(citation_gaps(REGISTER, read=lambda _path: "unrelated source"))

    def test_a_note_that_drops_its_boundary_fails_the_guard(self):
        """Deleting the correction must not silently re-license the absolute."""
        notes = _published_notes()
        entry = REGISTER[0]
        notes[entry.note] = notes[entry.note].replace(entry.bounds[0], "REDACTED")
        gaps = register_gaps(notes, REGISTER)
        self.assertTrue(
            any(entry.bounds[0] in gap for gap in gaps),
            f"a note stripped of its stated boundary stayed green: {gaps}",
        )

    def test_every_entry_records_why_it_was_approved(self):
        # An entry with no reason is an entry nobody can re-audit later.
        for entry in REGISTER:
            self.assertGreater(len(entry.why), 80, f"{entry.note}: reason too thin")
            self.assertTrue(entry.evidence, f"{entry.note}: no citation")
            self.assertTrue(entry.bounds, f"{entry.note}: no bounding phrase")


if __name__ == "__main__":
    unittest.main()
