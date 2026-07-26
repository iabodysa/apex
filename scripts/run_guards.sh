#!/bin/sh
# The one command that reproduces a CI guard lane on a workstation.
#
# Install the hooks that call it (one line, from the repo root):
#     git config core.hooksPath .githooks
#
# Every threshold and every scanner flag below is READ from the workflow that
# declares it rather than restated here. A guard written down twice drifts, and the
# copy that drifts is always the one a developer runs before pushing: it passes
# locally and reds in CI, or worse it passes in CI after a local red taught someone
# to wave reds through. Where a value genuinely cannot be read from one place, the
# `assert_lane_parity` check below fails loudly instead of letting the two rot apart.
#
# Modes:
#   tree              the Lint lane's content guards over the package
#   range <log-opts>  the redacted secret scan over a commit range (pre-push, CI)
#   thresholds        the declared scope and limits as JSON, for a tool that must
#                     gate on the same numbers instead of copying them
set -eu

MODE="${1:-tree}"
PACKAGE=apex
LANG_CODE=ar
MAX_MISSING=0

root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$root"

LINT_WORKFLOW=.github/workflows/lint.yml
TEST_WORKFLOW=.github/workflows/test.yml

# The stale cap is declared once, in the Lint workflow, next to the audit that
# justifies its value. Read it; never copy it.
read_stale_baseline() {
	if [ ! -f "$LINT_WORKFLOW" ]; then
		echo "guards: $LINT_WORKFLOW is missing, so the stale cap has no declaration to read" >&2
		exit 2
	fi
	value=$(sed -n 's/^[[:space:]]*STALE_BASELINE:[[:space:]]*\([0-9][0-9]*\).*$/\1/p' "$LINT_WORKFLOW")
	# A blank or multi-line capture both land in the reject arm: two declarations are
	# as broken as none, because neither tells us which one CI actually uses.
	case "$value" in
	"" | *[!0-9]*)
		echo "guards: cannot read exactly one STALE_BASELINE out of $LINT_WORKFLOW" >&2
		echo "guards: that file is the only declaration of the cap - repair it before trusting this run" >&2
		exit 2
		;;
	esac
	printf '%s' "$value"
}

# The remaining flags are structural constants that the Lint lane spells out in its
# own shell. They cannot be read out of it without parsing YAML, so assert instead
# that both sides still say the same thing. This is the honest second best: not one
# definition, but two that cannot silently disagree.
assert_lane_parity() {
	missing=""
	for fragment in \
		"python3 scripts/comment_audit.py $PACKAGE" \
		"--package $PACKAGE" \
		"--lang $LANG_CODE" \
		"--max-missing $MAX_MISSING" \
		'--max-stale "$STALE_BASELINE"'; do
		if ! grep -qF -- "$fragment" "$LINT_WORKFLOW"; then
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
}

tree_guards() {
	assert_lane_parity
	python3 scripts/comment_audit.py "$PACKAGE"
	python3 scripts/check_translations.py \
		--package "$PACKAGE" \
		--lang "$LANG_CODE" \
		--max-missing "$MAX_MISSING" \
		--max-stale "$(read_stale_baseline)"
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
	printf '{"package":"%s","lang":"%s","max_missing":%s,"max_stale":%s}\n' \
		"$PACKAGE" "$LANG_CODE" "$MAX_MISSING" "$(read_stale_baseline)"
	;;
*)
	echo "usage: scripts/run_guards.sh [tree|range <log-opts>|thresholds]" >&2
	exit 2
	;;
esac
