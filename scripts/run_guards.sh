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
#   tree              the Lint lane: ruff, the shell parse check, and the content guards
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

# Lift a named step's shell OUT of lint.yml and run that, instead of writing the command
# down a second time. A restated command is the drift this file exists to prevent, so
# where a step's whole body is the parameter there is nothing to assert parity about:
# the lane's own text is the only copy. Handles both `run:` forms - the inline scalar
# and the `|` block - and a step it cannot find is FATAL, because a mirror that quietly
# skips a gate it advertises is exactly the false PASS the header warns about.
workflow_step_shell() {
	step=$1
	shell=$(workflow_shell)
	body=$(printf '%s\n' "$shell" | awk -v want="$step" '
		/^[ ]*-[ ]+name:[ ]*/ {
			n = $0
			sub(/^[ ]*-[ ]+name:[ ]*/, "", n)
			instep = (n == want)
			inblock = 0
			next
		}
		inblock {
			if ($0 ~ /^[ ]*$/) { print ""; next }
			match($0, /^[ ]*/)
			if (indent < 0) indent = RLENGTH
			if (RLENGTH >= indent) { print substr($0, indent + 1); next }
			inblock = 0
			instep = 0
			next
		}
		instep && /^[ ]*run:[ ]*/ {
			r = $0
			sub(/^[ ]*run:[ ]*/, "", r)
			if (r == "|" || r == "|-" || r == ">" || r == ">-") {
				inblock = 1
				indent = -1
				next
			}
			print r
			instep = 0
			next
		}
	')
	if [ -z "$body" ]; then
		echo "guards: $LINT_WORKFLOW has no \"$step\" step with a run: body." >&2
		echo "guards: this script executes that step's own shell rather than a copy of it, so a" >&2
		echo "guards: renamed or deleted step leaves the gate UNRUN - reconcile the two before pushing." >&2
		exit 2
	fi
	printf '%s\n' "$body"
}

# Run the lane's step under a POSIX shell, and name the step when it reds so the failure
# reads as "CI would reject this", not as a local script blowing up.
run_lane_step() {
	step=$1
	command_text=$(workflow_step_shell "$step")
	if ! sh -c "$command_text"; then
		echo "guards: the Lint lane's \"$step\" step FAILS on this tree" >&2
		exit 1
	fi
}

# CI pins ruff because this repo's lint contract is ruff's DEFAULT rule set, and that set
# moves between minors - a workstation on another version renders a verdict that is not
# the lane's, in either direction. The pin is read out of the lane, never copied here.
# An absent ruff is fatal: the gate would silently not run, and a green with a gate
# missing is worse than a red.
check_ruff_version() {
	shell=$(workflow_shell)
	pinned=$(printf '%s\n' "$shell" | sed -n 's/.*pip install ruff==\([0-9.]*\).*/\1/p' | head -1)
	local_ruff=$(ruff --version 2>/dev/null | awk '{print $2}')
	if [ -z "$local_ruff" ]; then
		echo "guards: ruff is not on PATH, so the Lint lane's first gate CANNOT run here." >&2
		echo "guards: install the version the lane pins: pip install ruff==${pinned:-<see $LINT_WORKFLOW>}" >&2
		exit 2
	fi
	if [ -n "$pinned" ] && [ "$pinned" != "$local_ruff" ]; then
		echo "guards: NOTE - local ruff $local_ruff, CI pins $pinned; the default rule set moves" >&2
		echo "guards: between minors, so this ruff verdict is not the lane's" >&2
	fi
}

# The lane parses with the runner's /bin/sh, which is dash. A workstation's /bin/sh is
# whatever the OS ships - on macOS, bash in POSIX mode, which parses a few constructs
# dash rejects. The command is identical; the parser underneath is not, and that gap
# cannot be closed from here, so it gets said out loud instead of implied away.
note_sh_parser_drift() {
	if [ -n "$(/bin/sh -c 'echo ${BASH_VERSION:-}')" ]; then
		echo "guards: NOTE - /bin/sh here is bash in POSIX mode, CI's is dash; a few constructs" >&2
		echo "guards: dash would reject parse clean on this machine" >&2
	fi
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

# In the lane's own order, so the first red a developer sees here is the first red CI
# would show them.
tree_guards() {
	assert_lane_parity
	check_ruff_version
	run_lane_step "Run ruff"
	note_sh_parser_drift
	run_lane_step "Shell syntax"
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
