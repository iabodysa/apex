"""Capture the training-guide screenshots from synthetic rows, reproducibly.

WHAT IT IS FOR: docs/training/*.md marks where a screen belongs with a
`_[screenshot: ...]_` placeholder. This file turns one of those placeholders into
an actual image, from a site that holds nothing but the rows e2e/training_fixtures.py
invented, so nothing an operator would have to redact ever reaches the frame.

THE TWO PROPERTIES THAT MATTER

Privacy. Every visible value comes from the fixture file and carries its
`Training` prefix; the web-form shot is taken SIGNED OUT because a signed-in
session prefills the visitor's own name and email into it. Both shots are clipped
to the form, so the navbar - which carries the operator's name, avatar and unread
counts - is never in frame.

Determinism. Re-running has to produce the same bytes or a review cannot tell a
real UI change from noise, so everything that could drift is pinned: no dates or
ids are typed, animations are off (`reduced_motion`), the clock is UTC, the
device scale factor is 1, and each shot waits for a named element rather than for
a duration. Prove it rather than trusting it - capture into two directories and
compare the hashes:

    <bench>/env/bin/python e2e/training_shots_spec.py --out /tmp/shot-a
    <bench>/env/bin/python e2e/training_shots_spec.py --out /tmp/shot-b

PREREQUISITES
    1. That disposable site is being served on a port of its OWN:
           bench --site "$SITE_NAME" serve --port <free-port> --noreload
       A bench-wide `bench serve` is pinned to one site and ignores the site
       header, so BASE_URL has to reach a server started for this site or the
       capture silently reads whichever site that other server was started for.
    2. e2e/.env.local names it in SITE_NAME and points BASE_URL at that port.
    3. e2e/setup_screenshot_user.py and e2e/training_fixtures.py have both been
       run against that site.

The run prints one manifest line per image - site, route, role, language, app
version, repo commit, pixel size and SHA-256 - which is the evidence that says
which build and which rows an image actually shows.
"""
import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from e2e.desk_auth import (  # noqa: E402
    anonymous_page,
    assert_site,
    authenticated_page,
    declared_site,
)

REPO = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO / "docs" / "assets" / "training"

# The fixture prefix, restated so a failed shot names the file to run first.
FIXTURE_PREFIX = "Training"
BUILDING = f"{FIXTURE_PREFIX} Building B01"
ROOM = f"{FIXTURE_PREFIX} Room R01"

# Padding above the clipped region, in CSS pixels. A clip taken exactly on an
# element's box shaves the focus ring and the dropdown shadow, which reads as a
# rendering fault in the published image rather than as a tight crop. Small,
# because a few pixels more reaches the tab strip above the section.
PAD = 5


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _repo_commit():
    out = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout.strip() or "unknown"


def _app_version():
    init = (REPO / "apex" / "__init__.py").read_text()
    for line in init.splitlines():
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip("\"'")
    return "unknown"


def _park(page, selector, top=100):
    """Scroll ``selector`` to a FIXED distance from the top of the viewport.

    Not "scroll into view": that stops as soon as the element is visible, so the
    element lands wherever the previous interaction happened to leave the page
    and every clip taken from it is offset by a different amount. Parking it at a
    constant y makes the clip below reproducible.
    """
    page.evaluate(
        """([sel, top]) => {
            const el = document.querySelector(sel);
            if (!el) throw new Error('missing ' + sel);
            window.scrollTo(0, window.scrollY + el.getBoundingClientRect().top - top);
        }""",
        [selector, top],
    )
    page.wait_for_timeout(200)


def _clip_below(page, selector, width, height):
    """A clip rectangle anchored on ``selector`` and extending down over it.

    An element screenshot cannot be used for the Desk shot: it needs the link
    dropdown, which overflows the section, and Playwright clips an element shot
    to the element's own box exactly. Coordinates are rounded because a fractional
    origin resamples the image and two runs then differ in bytes while looking
    identical.
    """
    box = page.locator(selector).first.bounding_box()
    if not box:
        raise SystemExit(f"{selector} has no box - the page did not render it")
    return {
        "x": float(round(max(box["x"] - PAD, 0))),
        "y": float(round(max(box["y"] - PAD, 0))),
        "width": float(width),
        "height": float(height),
    }


def _region_text(page, selector):
    """Every word rendered inside ``selector``, as one flat line.

    A privacy review of an image otherwise means somebody squinting at it and
    saying it looked fine. Printing the region's own text puts the words that
    were on screen into the run record, where "is anything real in this frame"
    can be answered by reading a list instead of a picture - and where a later
    capture that quietly picks up a real row shows the difference in a diff.
    """
    raw = page.locator(selector).first.inner_text()
    return " / ".join(part.strip() for part in raw.splitlines() if part.strip())


def _pick_link(page, fieldname, typed, expected):
    """Fill a Link field the way an operator does - type a few letters, pick a row.

    Deliberately not frm.set_value(): on a new Housing Assignment it resolves
    without storing anything, so the Bed query stays unfiltered and the picture
    loses the one line it exists to show. Driving the control also proves the
    field is genuinely reachable at this role, which a programmatic write does not.

    ``typed`` is a PREFIX on purpose. Typing the full name and then clicking the
    row leaves the field empty - the control treats an input that already equals
    the option as nothing to complete - so the search would be silently unfiltered
    from then on. Waits on the STORED value, not on the click, because the click
    only starts the link validation the next field's query depends on.
    """
    field = f'[data-fieldname="{fieldname}"]'
    # Retried, because a new form re-renders its controls once after the document
    # exists: a pick that lands on the control being replaced is simply discarded,
    # silently and without an error, and the run would then screenshot an
    # unfiltered list while every wait it performed had passed.
    last = None
    for _attempt in range(4):
        box = page.locator(f"{field} input.input-with-feedback").first
        box.click()
        box.fill("")
        box.type(typed, delay=20)
        page.wait_for_selector(f'{field} .awesomplete [role="option"] strong')
        page.locator(f'{field} .awesomplete [role="option"]').first.click()
        page.wait_for_timeout(800)
        last = page.evaluate("(f) => (window.cur_frm && cur_frm.doc[f]) || ''", fieldname)
        if last == expected:
            # Close the list before returning. It stays open over the fields
            # BELOW it, and the next pick then times out clicking an input the
            # previous field's dropdown is covering.
            page.keyboard.press("Escape")
            page.wait_for_selector(
                f'{field} .awesomplete [role="option"]', state="hidden", timeout=5000
            )
            return
    raise SystemExit(f"{fieldname}: picked {typed!r} but the form holds {last!r}, wanted {expected!r}")


def shot_assignment_bed_selection(page, base, out_dir):
    """Desk: the Bed link dropdown on a new Housing Assignment, filtered to a room.

    The lesson step this illustrates is "select an available bed", and the point
    of the picture is the filter line under the results - it is what tells a
    supervisor why a bed they expected is missing from the list.
    """
    page.goto(f"{base}/app/housing-assignment/new", wait_until="networkidle")
    # Against the DECLARED site, never against what the page just said about
    # itself: comparing the page to itself always passes and proves nothing.
    assert_site(page, declared_site())
    page.wait_for_function("() => window.cur_frm && cur_frm.doc && cur_frm.doc.doctype")
    _pick_link(page, "building", f"{FIXTURE_PREFIX} Building", BUILDING)
    _pick_link(page, "room", f"{FIXTURE_PREFIX} Room", ROOM)

    section = '.form-section:has([data-fieldname="bed"])'
    _park(page, section)
    bed = page.locator('[data-fieldname="bed"] input.input-with-feedback').first
    bed.click()
    bed.type(f"{FIXTURE_PREFIX} Bed", delay=20)
    # Wait for the two fixture rows AND the filter line, not for a duration: the
    # dropdown opens empty while the search request is in flight, and the filter
    # line - the whole subject of this picture - arrives with the results.
    page.wait_for_function(
        """() => {
            const ul = document.querySelector('[data-fieldname="bed"] .awesomplete ul');
            if (!ul) return false;
            const rows = ul.querySelectorAll('[role="option"]');
            return rows.length >= 2 && ul.innerText.includes('Filters applied');
        }"""
    )
    clip = _clip_below(page, section, width=1180, height=487)
    target = out_dir / "accommodation" / "housing-assignment-bed-selection-en.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(target), clip=clip)
    return target, {
        "route": "/app/housing-assignment/new",
        "lang": "en",
        "auth": "desk",
        "text": _region_text(page, section),
    }


def shot_resident_request_ar(page, base, out_dir):
    """Web form: the resident-facing Housing Request intake, in Arabic, signed out.

    Signed out because a logged-in session prefills its own name and email into
    this form. Only the three Select fields are set, and only to options the app
    itself ships and translates - so every character in the frame comes from the
    product, and no sentence had to be invented to stand in for a resident's. The
    name, mobile and description fields are left EMPTY on purpose: they are the
    three that carry a person, and an empty one cannot leak.
    """
    page.context.add_cookies(
        [{"name": "preferred_language", "value": "ar", "url": base}]
    )
    page.goto(f"{base}/qr-request/new", wait_until="networkidle")
    page.wait_for_selector('[data-fieldname="request_category"]')
    page.evaluate(
        """() => {
            const set = (name, value) => {
                const el = document.querySelector(`[data-fieldname="${name}"] select`);
                if (!el) throw new Error('missing select ' + name);
                el.value = value;
                el.dispatchEvent(new Event('change', {bubbles: true}));
            };
            set('requester_type', 'Anonymous');
            set('preferred_language', 'Arabic');
            set('request_category', 'Maintenance');
            set('issue_location', 'Room');
        }"""
    )
    # The container, not the <form>: the form element starts below the page title,
    # and a screenshot without the title does not say which screen it is.
    form = page.locator(".web-form-container").first
    form.wait_for(state="visible")
    target = out_dir / "accommodation" / "resident-request-intake-ar.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    form.screenshot(path=str(target))
    return target, {
        "route": "/qr-request/new",
        "lang": "ar",
        "auth": "guest",
        "text": _region_text(page, ".web-form-container"),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help="directory to write the lesson folders into (default: docs/assets/training)",
    )
    args = parser.parse_args(argv)
    out_dir = Path(args.out).resolve()

    commit = _repo_commit()
    version = _app_version()
    results = []

    with authenticated_page() as (page, base):
        results.append(shot_assignment_bed_selection(page, base, out_dir))
        site = page.evaluate("() => frappe.boot.sitename")
        role = page.evaluate("() => frappe.session.user")

    with anonymous_page() as (page, base):
        results.append(shot_resident_request_ar(page, base, out_dir))

    print(f"site={site} session_user={role} app_version={version} commit={commit}")
    for target, meta in results:
        print(
            f"{target.relative_to(out_dir)} "
            f"route={meta['route']} lang={meta['lang']} auth={meta['auth']} "
            f"bytes={target.stat().st_size} sha256={_sha256(target)}"
        )
        print(f"    on screen: {meta['text']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
