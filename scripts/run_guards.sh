#!/bin/sh
# The one command that reproduces a CI guard lane on a workstation.
#
# Install the hooks that call it (one line, from the repo root):
#     git config core.hooksPath .githooks
#
# No threshold below is a second copy of a number CI decides. A guard written down
# twice drifts, and the copy that drifts is always the one a developer runs before
# pushing: it passes locally and reds in CI, or worse it passes in CI after a local red
# taught someone to wave reds through. Where a value genuinely cannot be read from one
# place, `assert_lane_parity` fails loudly instead of letting the two rot apart.
#
# Modes:
#   tree              the Lint lane's content guards over the package
#   range <log-opts>  the redacted secret scan over a commit range (pre-push, CI)
#   thresholds        the declared scope and limits as JSON, for a tool that must
#                     gate on the same declaration instead of copying it
set -eu

MODE="${1:-tree}"
PACKAGE=apex
LANG_CODE=ar
MAX_MISSING=0

root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$root"

LINT_WORKFLOW=.github/workflows/lint.yml
TEST_WORKFLOW=.github/workflows/test.yml

# Read the workflow's SHELL, never its prose: lint.yml explains in a comment why it no
# longer passes --max-stale, and a naive grep would read that sentence as the flag.
workflow_shell() {
	if [ ! -f "$LINT_WORKFLOW" ]; then
		echo "guards: $LINT_WORKFLOW is missing, so there is nothing to mirror" >&2
		echo "guards: a local pass would stop meaning a CI pass - repair it before trusting this run" >&2
		exit 2
	fi
	grep -v '^[[:space:]]*#' "$LINT_WORKFLOW"
}

# The Lint lane spells its flags out in its own shell, and they cannot be read out of
# it without parsing YAML, so assert instead that both sides still say the same thing.
# This is the honest second best: not one definition, but two that cannot silently
# disagree.
#
# The stale ratchet has NO parameter left to mirror. It used to be a number, read out
# of lint.yml so this file held no copy of it; it is now the recorded set in
# apex/translations/<lang>.stale-baseline.txt, which both lanes read out of the same
# commit. Nothing is passed, so nothing can drift - which is why a returning
# --max-stale is rejected below as hard as a missing flag.
assert_lane_parity() {
	shell=$(workflow_shell)

	missing=""
	for fragment in \
		"python3 scripts/comment_audit.py $PACKAGE" \
		"python3 scripts/check_translations.py" \
		"--package $PACKAGE" \
		"--lang $LANG_CODE" \
		"--max-missing $MAX_MISSING"; do
		if ! printf '%s\n' "$shell" | grep -qF -- "$fragment"; then
			missing="$missing
  $fragment"
		fi
	done
	if [ -n "$missing" ]; then
		echo "guards: $LINT_WORKFLOW no longer invokes the guards this script mirrors." >&2
		echo "guards: absent from the workflow:$missing" >&2
		echo "guards: a local pass would stop meaning a CI pass - reconcile the two before pushing." >&2
		exit 2
	fi

	if printf '%s\n' "$shell" | grep -q -- "--max-stale"; then
		echo "guards: $LINT_WORKFLOW passes --max-stale again, so this script no longer" >&2
		echo "guards: runs what CI runs. The stale ratchet is a recorded SET, not a number:" >&2
		echo "guards: drop the flag and re-record the set with" >&2
		echo "  python3 scripts/check_translations.py --package $PACKAGE --lang $LANG_CODE --update-stale-baseline" >&2
		exit 2
	fi
}

tree_guards() {
	assert_lane_parity
	python3 scripts/comment_audit.py "$PACKAGE"
	python3 scripts/check_translations.py \
		--package "$PACKAGE" \
		--lang "$LANG_CODE" \
		--max-missing "$MAX_MISSING"
	python3 scripts/check_doctype_dates.py "$PACKAGE"
}

# CI pins the scanner version; a workstation cannot be forced to match, so report the
# gap rather than pretending a different rule set is the same gate.
warn_on_scanner_version_drift() {
	# A note, never a gate: an absent workflow must not abort a scan that can still run.
	[ -f "$TEST_WORKFLOW" ] || return 0
	pinned=$(sed -n 's/^[[:space:]]*GITLEAKS_VERSION=\([0-9.]*\).*$/\1/p' "$TEST_WORKFLOW" | head -1)
	local_version=$(gitleaks version 2>/dev/null | tr -d ' \n')
	if [ -n "$pinned" ] && [ -n "$local_version" ] && [ "$pinned" != "$local_version" ]; then
		echo "guards: NOTE - local gitleaks $local_version, CI pins $pinned; findings can differ" >&2
	fi
}

# Redaction is not optional: an unredacted finding copies the secret into a log that
# outlives the commit it came from. A missing binary is loud on a workstation and
# fatal under CI, because a silent pass leaves the lane green with nothing scanned.
secret_scan() {
	if command -v gitleaks >/dev/null 2>&1; then
		warn_on_scanner_version_drift
		gitleaks detect --no-banner --redact --source . --log-opts="$1"
	elif [ -n "${CI:-}" ]; then
		echo "guards: gitleaks is required in CI and was not found on PATH" >&2
		return 1
	else
		echo "guards: WARNING - gitleaks is not installed, the secret scan DID NOT RUN" >&2
		echo "guards: install it (brew install gitleaks) so this machine matches CI" >&2
	fi
}

case "$MODE" in
tree)
	tree_guards
	;;
range)
	secret_scan "${2:?range mode needs git log options, e.g. origin/apex..HEAD}"
	;;
thresholds)
	# The stale ratchet reports a PATH, not a number: the set recorded in that file is
	# the whole parameter, and it is the same file in both lanes.
	assert_lane_parity
	printf '{"package":"%s","lang":"%s","max_missing":%s,"stale_baseline":"%s"}\n' \
		"$PACKAGE" "$LANG_CODE" "$MAX_MISSING" \
		"$PACKAGE/translations/$LANG_CODE.stale-baseline.txt"
	;;
*)
	echo "usage: scripts/run_guards.sh [tree|range <log-opts>|thresholds]" >&2
	exit 2
	;;
esac
