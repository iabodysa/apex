#!/bin/sh
# The one command that reproduces the CI guards a workstation can run - which come from
# more than one lane, and are reported under the lane each was read out of.
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
#   tree              every frappe-free CI guard a workstation can run: ruff, the shell
#                     parse check, and the content guards. These do NOT all come from one
#                     workflow, so each is reported under the lane it was read out of and
#                     the run ends with a per-lane count - a PASS here is not a PASS of
#                     any single lane, and a red names the workflow to go and read
#   range <log-opts>  the redacted secret scan over a commit range (pre-push, CI)
#   thresholds        the declared scope and limits as JSON, for a tool that must
#                     gate on the same declaration instead of copying it
#   doctor [--fix]    whether the hooks in THIS work tree will actually run on it. Every
#                     other mode above answers "does the content pass"; this one answers
#                     the question underneath it, "did any gate run at all", which is the
#                     failure that leaves no trace in a log
set -eu

MODE="${1:-tree}"
PACKAGE=apex
LANG_CODE=ar
MAX_MISSING=0

root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$root"

WORKFLOW_DIR=.github/workflows
TEST_WORKFLOW=$WORKFLOW_DIR/test.yml

# WHICH LANE a guard belongs to is a fact about the repository, not one this script gets
# to assert. Every guard below is looked up by STEP NAME across all workflows, and is
# reported under the `name:` of the file it was actually found in - so moving a step from
# one workflow to another moves its attribution with it, and there is no table here to
# forget to update. This matters because tree mode is not one lane: the DocType contract
# lives in the Tests workflow while ruff and the content guards live in Lint, and a run
# that printed neither name let a reader take a two-lane PASS for a one-lane one and sent
# a failure hunt to the wrong file.
WORKFLOWS=""
LANES_COVERED=""
STEP_LANE=""
STEP_BODY=""
STEP_WORKFLOW=""

discover_workflows() {
	# Both extensions: GitHub reads either, and a step that moved into a .yaml file
	# would otherwise report as owned by nobody.
	WORKFLOWS=$(ls -1 "$WORKFLOW_DIR"/*.yml "$WORKFLOW_DIR"/*.yaml 2>/dev/null || true)
	if [ -z "$WORKFLOWS" ]; then
		echo "guards: $WORKFLOW_DIR holds no workflow, so there is nothing to mirror" >&2
		echo "guards: a local pass would stop meaning a CI pass - repair it before trusting this run" >&2
		exit 2
	fi
}

# The lane's human name, read out of the workflow itself, so the label printed here is
# the one GitHub prints on the check a developer then goes to open.
lane_name() {
	name=$(sed -n 's/^name:[[:space:]]*//p' "$1" | head -1)
	if [ -z "$name" ]; then
		name=$(basename "$1")
	fi
	printf '%s\n' "$name"
}

# Read a workflow's SHELL, never its prose: lint.yml explains in a comment why it no
# longer passes --max-stale, and a naive grep would read that sentence as the flag.
workflow_shell() {
	file=$1
	if [ ! -f "$file" ]; then
		echo "guards: $file is missing, so there is nothing to mirror" >&2
		echo "guards: a local pass would stop meaning a CI pass - repair it before trusting this run" >&2
		exit 2
	fi
	grep -v '^[[:space:]]*#' "$file"
}

# Lift a named step's shell OUT of a workflow and run that, instead of writing the command
# down a second time. A restated command is the drift this file exists to prevent, so
# where a step's whole body is the parameter there is nothing to assert parity about:
# the lane's own text is the only copy. Handles both `run:` forms - the inline scalar and
# the `|` block. Empty means this workflow does not own the step; locate_step below
# decides what that means, because only it can see whether another workflow does.
step_body() {
	wf_file=$1
	wf_step=$2
	workflow_shell "$wf_file" | awk -v want="$wf_step" '
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
	'
}

# Find the ONE workflow that owns a step, and remember its shell, its file and its lane.
# A step no workflow owns is FATAL, because a mirror that quietly skips a gate it
# advertises is exactly the false PASS the header warns about. Two workflows owning the
# same name is fatal too, rather than first-wins: the lane would then be a guess, and
# every line this script prints presents it as a fact.
locate_step() {
	step=$1
	[ -n "$WORKFLOWS" ] || discover_workflows
	STEP_LANE=""
	STEP_BODY=""
	STEP_WORKFLOW=""
	owners=""
	for wf in $WORKFLOWS; do
		body=$(step_body "$wf" "$step")
		[ -n "$body" ] || continue
		owners="$owners $wf"
		STEP_WORKFLOW=$wf
		STEP_LANE=$(lane_name "$wf")
		STEP_BODY=$body
	done
	if [ -z "$STEP_BODY" ]; then
		echo "guards: no workflow under $WORKFLOW_DIR has a \"$step\" step with a run: body." >&2
		echo "guards: this script executes that step's own shell rather than a copy of it, so a" >&2
		echo "guards: renamed or deleted step leaves the gate UNRUN - reconcile the two before pushing." >&2
		exit 2
	fi
	set -- $owners
	if [ $# -gt 1 ]; then
		echo "guards: \"$step\" has a run: body in $# workflows:$owners" >&2
		echo "guards: the lane this script reports would then be a guess. Rename one of them, so" >&2
		echo "guards: attribution stays derived from the file the step was actually read out of." >&2
		exit 2
	fi
}

# CI runs the lane inside a fresh CHECKOUT, which holds only what git tracks. A
# workstation runs it inside a work tree that also holds ignored scratch, and the lane
# hands ruff two DIRECTORIES to walk rather than a file list - so ruff decides for itself
# what is in scope, and with two roots that decision is not stable. Measured here, with a
# gitignored apex/demo/*.py present, `ruff check apex/ scripts/` alternated between
# "All checks passed" and "Found 7 errors" across back-to-back runs with the cache
# untouched (P F P P F P F F F F F F P F F), while the same command with a single root
# honoured .gitignore 20 times out of 20. The hook environment is not the variable: the
# same command scored 7/20 bare and 7/20 under the GIT_DIR the pre-push hook exports.
# So the lane's own text, pointed at a work tree, is a coin flip CI can never reproduce -
# a fresh clone has no such file to find, which is why the lane itself stays green.
#
# comment_audit, check_translations and check_doctype_dates each draw this boundary for
# themselves, with `git ls-files --cached --others --exclude-standard`, so those three run
# in the work tree where CI runs them. Rewriting a lifted step's command here to add the
# boundary is the drift this file exists to prevent, so for the steps that DO walk a
# directory they were handed, the boundary is applied to the step's INPUT instead - the
# same file set, materialised, with this work tree's current contents so an uncommitted
# edit is still graded. Only what a clone would never receive is left behind.
CI_TREE=""

build_ci_tree() {
	CI_TREE=$(mktemp -d) || {
		echo "guards: cannot create a temporary directory to mirror the checkout in" >&2
		exit 2
	}
	trap 'rm -rf "$CI_TREE"' EXIT INT TERM
	if ! git ls-files -z --cached --others --exclude-standard |
		python3 -c '
import os, shutil, sys

dest = sys.argv[1]
raw = sys.stdin.buffer.read().decode("utf-8", "surrogateescape")
names = [name for name in raw.split("\0") if name]
if not names:
    sys.exit(1)
for name in names:
    # A tracked file deleted from the work tree cannot be graded here; the lane would
    # not see it either, because the deletion is what gets pushed.
    if not os.path.isfile(name):
        continue
    target = os.path.join(dest, name)
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    shutil.copy2(name, target)
' "$CI_TREE"; then
		echo "guards: git could not list the files a fresh clone would hold, so this run" >&2
		echo "guards: would grade a tree CI never sees - repair the work tree before pushing." >&2
		exit 2
	fi
}

# Run a lifted step under a POSIX shell and NAME the lane it came from, both before it
# runs and if it reds - so a pass says which lanes it spanned instead of implying one, and
# a failure reads as "this workflow would reject this", not as a local script blowing up.
# `where` is the directory to run it in: the materialised checkout for a step handed a
# directory to walk, the work tree for one that asks git for its own file set.
run_lane_step() {
	lane_step=$1
	lane_where=$2
	locate_step "$lane_step"
	echo "guards: [$STEP_LANE] $lane_step"
	LANES_COVERED="$LANES_COVERED$STEP_LANE
"
	if ! (cd "$lane_where" && sh -c "$STEP_BODY"); then
		echo "guards: the $STEP_LANE lane's \"$lane_step\" step FAILS on this tree" >&2
		exit 1
	fi
}

# Say out loud what the PASS actually covered. The counts come from the steps that ran,
# grouped by the workflow each was read out of, so no lane can be credited with a guard
# that lives somewhere else - and no lane can be read as fully passed, because tree mode
# only ever runs the frappe-free subset of one.
report_lanes_covered() {
	echo "guards: PASS - steps run, by the lane each was read out of:"
	printf '%s' "$LANES_COVERED" | sort | uniq -c | while read -r count lane; do
		echo "guards:   $lane: $count"
	done
	echo "guards: each lane is covered only for the steps listed - the rest of its steps"
	echo "guards: (bench install, full suite, portal builds) are not mirrored on a workstation."
}

# CI pins ruff because this repo's lint contract is ruff's DEFAULT rule set, and that set
# moves between minors - a workstation on another version renders a verdict that is not
# the lane's, in either direction. The pin is read out of the lane, never copied here -
# and out of whichever workflow the "Run ruff" step was found in, so a lane move carries
# the pin with it. An absent ruff is fatal: the gate would silently not run, and a green
# with a gate missing is worse than a red.
check_ruff_version() {
	locate_step "Run ruff"
	ruff_lane=$STEP_LANE
	ruff_workflow=$STEP_WORKFLOW
	pinned=$(workflow_shell "$ruff_workflow" |
		sed -n 's/.*pip install ruff==\([0-9.]*\).*/\1/p' | head -1)
	local_ruff=$(ruff --version 2>/dev/null | awk '{print $2}')
	if [ -z "$local_ruff" ]; then
		echo "guards: ruff is not on PATH, so the $ruff_lane lane's first gate CANNOT run here." >&2
		echo "guards: install the version it pins: pip install ruff==${pinned:-<see $ruff_workflow>}" >&2
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

# The guard COMMANDS are no longer restated here - every one is lifted from the step that
# owns it - so the only thing left that could drift is the declaration `thresholds` mode
# publishes as JSON for a tool to gate on. That declaration is asserted against the BODY
# of the steps it describes, not against a workflow file named here, so it keeps agreeing
# with the guard wherever the guard's step lives.
#
# The stale ratchet has NO parameter left to mirror. It used to be a number, read out
# of the lane so this file held no copy of it; it is now the recorded set in
# apex/translations/<lang>.stale-baseline.txt, which both lanes read out of the same
# commit. Nothing is passed, so nothing can drift - which is why a returning
# --max-stale is rejected below as hard as a missing flag.
assert_lane_parity() {
	locate_step "Comment policy (why-not-what, no banners, no task ids)"
	comments_body=$STEP_BODY
	locate_step "Arabic translation coverage"
	translations_body=$STEP_BODY
	translations_lane=$STEP_LANE

	missing=""
	if ! printf '%s\n' "$comments_body" | grep -qF -- "scripts/comment_audit.py $PACKAGE"; then
		missing="$missing
  scripts/comment_audit.py $PACKAGE"
	fi
	for fragment in \
		"--package $PACKAGE" \
		"--lang $LANG_CODE" \
		"--max-missing $MAX_MISSING"; do
		if ! printf '%s\n' "$translations_body" | grep -qF -- "$fragment"; then
			missing="$missing
  $fragment"
		fi
	done
	if [ -n "$missing" ]; then
		echo "guards: the $translations_lane lane no longer runs the guards on the scope this" >&2
		echo "guards: script declares. Absent from the step bodies:$missing" >&2
		echo "guards: a local pass would stop meaning a CI pass - reconcile the two before pushing." >&2
		exit 2
	fi

	if printf '%s\n' "$translations_body" | grep -q -- "--max-stale"; then
		echo "guards: the $translations_lane lane passes --max-stale again, so this script no" >&2
		echo "guards: longer runs what CI runs. The stale ratchet is a recorded SET, not a number:" >&2
		echo "guards: drop the flag and re-record the set with" >&2
		echo "  python3 scripts/check_translations.py --package $PACKAGE --lang $LANG_CODE --update-stale-baseline" >&2
		exit 2
	fi
}

# In the Lint lane's own order, so the first red a developer sees here is the first red
# that lane would show them - with the one guard that belongs to a DIFFERENT workflow run
# last and labelled as such, rather than folded in silently.
#
# The last three steps are NOT run against the materialised tree: each already asks git
# for its own file set, so here they run where CI runs them, in a work tree, on the code
# path their lane exercises. Only the first two, which walk directories they were handed,
# need the boundary supplied for them.
tree_guards() {
	discover_workflows
	assert_lane_parity
	check_ruff_version
	build_ci_tree
	run_lane_step "Run ruff" "$CI_TREE"
	note_sh_parser_drift
	run_lane_step "Shell syntax" "$CI_TREE"
	run_lane_step "Comment policy (why-not-what, no banners, no task ids)" "$root"
	run_lane_step "Arabic translation coverage" "$root"
	run_lane_step "DocType date and layout contract" "$root"
	report_lanes_covered
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

# A guard that never ran leaves no red to read, which is the one failure the modes above
# cannot report on themselves: they only ever speak about a tree git already handed them.
# Everything below judges the WIRING - whether the hooks committed in this work tree are
# the hooks git would actually execute here - and it is the standing answer to "is the
# local gate live", asked without having to remember what to look at.
HOOKS_DIRNAME=.githooks
HOOKED_FILES="commit-msg pre-commit pre-push"
DOCTOR_FAULTS=0
DOCTOR_FOREIGN=0

# Canonical form or nothing: two spellings of one directory must not read as two
# directories, and a path that cannot be entered is not a hooks directory at all.
# `pwd -P` because the comparison below is an identity test and the two sides arrive
# spelled differently - git reports a resolved work tree root while a configured value
# keeps whatever symlink it was written with, so a logical pwd reports one directory
# reached two ways as a mismatch (/var against /private/var on macOS).
canonical_dir() {
	(CDPATH= cd -- "$1" 2>/dev/null && pwd -P) || return 1
}

# Git runs a hook from the work tree root, so a RELATIVE core.hooksPath resolves per
# work tree and an absolute one pins every linked work tree to whichever checkout the
# value was written from. That difference is the whole subject of this mode.
resolved_hooks_dir() {
	case "$1" in
	/*) printf '%s\n' "$1" ;;
	*) printf '%s\n' "$root/$1" ;;
	esac
}

# How many work trees hold no .githooks of their own. A foreign absolute value is the only
# thing gating those, so this count is what makes the repair below refusable on evidence
# rather than on caution. Prints NOTHING when the enumeration itself fails, because a
# repair that proceeds on an unreadable fleet is the fail-open this count exists to close.
trees_without_hooks() {
	listing=$(git worktree list --porcelain 2>/dev/null) || return 1
	[ -n "$listing" ] || return 1
	printf '%s\n' "$listing" |
		while read -r key value; do
			[ "$key" = "worktree" ] || continue
			[ -d "$value/$HOOKS_DIRNAME" ] || echo x
		done | wc -l | tr -d ' '
}

doctor_fault() {
	DOCTOR_FAULTS=$((DOCTOR_FAULTS + 1))
	echo "doctor: FAIL - $1" >&2
}

# Setting a path that currently resolves nowhere can only ADD gating: no hook runs today,
# and afterwards the work trees that carry .githooks are gated while the ones that do not
# are exactly as unguarded as they already were. That is the whole test for whether a
# repair is safe to write, and it is why the live case below is refused instead.
#
# A condition this run has just repaired is NOT counted as a fault. Exiting non-zero after
# fixing the thing would train a caller to ignore this mode's exit code, which is the only
# part of it a script can read.
repair_hooks_path() {
	if [ "$DOCTOR_FIX" -eq 1 ]; then
		git config core.hooksPath "$HOOKS_DIRNAME"
		echo "doctor: $1"
		echo "doctor: repaired - core.hooksPath is now $HOOKS_DIRNAME"
		return 0
	fi
	doctor_fault "$1"
	echo "doctor: re-run with --fix to set it, or by hand: git config core.hooksPath $HOOKS_DIRNAME" >&2
}

check_hooks_path() {
	configured=$(git config --get core.hooksPath || true)

	if [ -z "$configured" ]; then
		repair_hooks_path "core.hooksPath is unset, so no commit-msg, pre-commit or pre-push
doctor:        hook runs here and every local gate is silently skipped"
		return 0
	fi

	target=$(resolved_hooks_dir "$configured")
	if [ ! -d "$target" ]; then
		repair_hooks_path "core.hooksPath names $configured, which does not exist. git skips a
doctor:        missing hooks directory without a word, so the local gate is dead"
		return 0
	fi

	here=$(canonical_dir "$root/$HOOKS_DIRNAME" || true)
	there=$(canonical_dir "$target" || true)
	[ "$here" = "$there" ] && return 0

	# Not a fault: this value is what keeps the hookless work trees gated at all. It is
	# reported because it means an edit to .githooks or to a gate script in THIS tree is
	# never exercised by the author who made it - the hooks that fire belong elsewhere.
	DOCTOR_FOREIGN=1
	stale=$(trees_without_hooks || true)
	echo "doctor: NOTE - the hooks that fire here are $there, not $root/$HOOKS_DIRNAME" >&2
	echo "doctor: so an edit to $HOOKS_DIRNAME/ or scripts/ in this tree is not exercised by its own" >&2
	echo "doctor: author, and a clone or a move of this checkout finds no hooks at all." >&2

	# The count IS the precondition, measured rather than remembered. While any work tree
	# carries no hooks of its own, this foreign value is the only thing gating it and
	# rewriting it would convert a latent portability defect into an active outage on every
	# one of them. Once nothing depends on it, the same command performs the repair.
	if [ -z "$stale" ]; then
		echo "doctor: NOT repaired: the work trees could not be enumerated, so there is no" >&2
		echo "doctor: evidence that rewriting this value would leave every one of them gated." >&2
		return 0
	fi
	if [ "$stale" -gt 0 ]; then
		echo "doctor: NOT repaired, and --fix will not repair it: $stale work trees hold no" >&2
		echo "doctor: $HOOKS_DIRNAME of their own, and this value is the only thing gating them today." >&2
		echo "doctor: re-run once that count reaches zero and --fix will set $HOOKS_DIRNAME." >&2
		return 0
	fi
	if [ "$DOCTOR_FIX" -eq 0 ]; then
		echo "doctor: every work tree now carries its own $HOOKS_DIRNAME, so this is safe to repair:" >&2
		echo "doctor: re-run with --fix, or by hand: git config core.hooksPath $HOOKS_DIRNAME" >&2
		return 0
	fi
	git config core.hooksPath "$HOOKS_DIRNAME"
	DOCTOR_FOREIGN=0
	echo "doctor: repaired - core.hooksPath is now $HOOKS_DIRNAME, resolved per work tree"
}

# git skips a hook it cannot execute and says nothing, which is the quietest way for this
# gate to stop existing - so the bit is checked rather than the file's presence.
check_hooks_executable() {
	for hook in $HOOKED_FILES; do
		path="$root/$HOOKS_DIRNAME/$hook"
		if [ ! -f "$path" ]; then
			doctor_fault "$HOOKS_DIRNAME/$hook is missing from this work tree"
			continue
		fi
		[ -x "$path" ] && continue
		if [ "$DOCTOR_FIX" -eq 1 ]; then
			chmod +x "$path"
			echo "doctor: made $HOOKS_DIRNAME/$hook executable"
			continue
		fi
		doctor_fault "$HOOKS_DIRNAME/$hook is not executable, so git skips it in silence"
	done
}

# The gates the hooks reach have to exist for the hooks to mean anything: pre-commit and
# commit-msg both refuse the commit outright when the metadata gate is absent, and
# pre-push degrades to a warning when this runner is, so an absent file here is the
# difference between a gate and a printed sentence.
check_gates_reachable() {
	for gate in scripts/check_commit_metadata.py scripts/run_guards.sh; do
		[ -f "$root/$gate" ] || doctor_fault "$gate is absent, so the hooks that call it cannot gate"
	done
	command -v python3 >/dev/null 2>&1 ||
		doctor_fault "python3 is not on PATH, so the commit metadata gate refuses every commit"
}

hook_doctor() {
	check_hooks_path
	check_hooks_executable
	check_gates_reachable
	if [ "$DOCTOR_FAULTS" -ne 0 ]; then
		echo "doctor: $DOCTOR_FAULTS fault(s) - the local gate is not live on this work tree" >&2
		exit 1
	fi
	if [ "$DOCTOR_FOREIGN" -eq 1 ]; then
		echo "doctor: PASS - a gate is live here, but it is another checkout's copy (see the NOTE)"
		return 0
	fi
	echo "doctor: PASS - the hooks in this work tree are the hooks git runs here"
}

case "$MODE" in
tree)
	tree_guards
	;;
doctor)
	DOCTOR_FIX=0
	[ "${2:-}" = "--fix" ] && DOCTOR_FIX=1
	hook_doctor
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
	echo "usage: scripts/run_guards.sh [tree|range <log-opts>|thresholds|doctor [--fix]]" >&2
	exit 2
	;;
esac
