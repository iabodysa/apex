# Non-DocType Artefact Census Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Grade every non-DocType, non-portal artefact Apex ships — 370 of them — against one fixed codebook, and produce a single JSON report that says, per artefact, whether it is needed, whether its structure is right, and whether its name is right.

**Architecture:** A mechanical census runs first and answers, with certainty and no tokens, every question a script can decide. Only the residue — the questions that need judgement — is handed to agents, in slices the script enumerates, never slices an agent computes for itself. A planted defect proves the harness can fail before any verdict is believed.

**Tech Stack:** Python 3 for the census and the aggregator; `ctl` for the run; Sonnet subagents for the judgement pass; JSON as the only interchange format.

## Global Constraints

- The population is **370 artefacts**: number_card 113, report 47, dashboard_chart 46, onboarding_step 42, notification 34, print_format 25, workflow 16, form_tour 13, page 11, workspace 10, module_onboarding 6, web_form 6, dashboards 11. DocTypes (156) and the portal are out of scope.
- **The codebook is fixed at 14 questions.** It is not a target to grow toward. A question that cannot change what a reader does is cut before the run, not after.
- **Every question is classified `mechanical` or `judgement` before the run.** A mechanical question is answered by the census script and is never sent to an agent.
- **No agent computes its own slice.** The script writes each agent's exact item list to a file and the brief interpolates it.
- **Every fan-out reports its own coverage**: `expected N, distinct M, duplicated K, unopened J`. `unopened > 0` voids the verdict; it does not round down.
- **A planted defect must survive to the report.** If the canary is not caught, the run is void regardless of what else it found.
- Concurrency is capped at 16 agents; that is a ceiling, not a target.
- Output is one file: `.claude/audits/artefact-census.json`.

---

## File Structure

- `Create: .claude/tools/census/enumerate.py` — walks `apex/**`, emits one record per artefact with its measurable facts. No judgement, no network, no writes to the repo.
- `Create: .claude/tools/census/codebook.py` — the 14 questions as data: id, text, kind (`mechanical`/`judgement`), and for mechanical ones the function that answers it.
- `Create: .claude/tools/census/aggregate.py` — joins agent verdicts back onto the census, asserts the join, computes coverage and disagreement, writes the final report.
- `Create: .claude/audits/artefact-census.json` — the deliverable.
- `Modify: none.` This plan grades the app; it does not change it. Fixes are carded from the report afterwards.

---

### Task 1: The census script

**Files:**
- Create: `.claude/tools/census/enumerate.py`
- Test: `.claude/tools/census/test_enumerate.py`

**Interfaces:**
- Produces: `enumerate_artefacts(app_root: str) -> list[dict]`, each dict carrying `kind`, `name`, `path`, `module`, `folder_matches_name`, `is_standard`, `parses`, `referenced_by` (list of workspace names), `reaches_operator` (bool), `size_bytes`.

- [ ] **Step 1: Write the failing test**

```python
def test_every_artefact_kind_is_counted():
    records = enumerate_artefacts("apex")
    counts = collections.Counter(r["kind"] for r in records)
    assert counts["number_card"] == 113
    assert counts["dashboard_chart"] == 46
    assert counts["report"] == 47
    assert sum(counts.values()) == 370

def test_reaches_operator_excludes_back_engines():
    records = {r["name"]: r for r in enumerate_artefacts("apex") if r["kind"] == "dashboard_chart"}
    assert all(not r["reaches_operator"] for r in records.values())
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python3 -m pytest .claude/tools/census/test_enumerate.py -v`
Expected: FAIL with `ModuleNotFoundError` / `NameError: enumerate_artefacts`.

- [ ] **Step 3: Implement the walker**

```python
KINDS = ("number_card", "report", "dashboard_chart", "onboarding_step", "notification",
         "print_format", "workflow", "form_tour", "page", "workspace",
         "module_onboarding", "web_form", "salis_dashboard", "habitat_dashboard")
BACK_ENGINES = "apex/apex_core/workspace/back_engines/back_engines.json"

def enumerate_artefacts(app_root):
    operator_text, back_text = _workspace_texts(app_root)
    records = []
    for kind in KINDS:
        for folder in _folders_of_kind(app_root, kind):
            name, parses = _read_name(folder)
            records.append({
                "kind": kind,
                "name": name,
                "path": folder,
                "module": _module_of(folder),
                "folder_matches_name": _slug(name) == os.path.basename(folder),
                "is_standard": _read_flag(folder, "is_standard"),
                "parses": parses,
                "referenced_by": _workspaces_naming(name, app_root),
                "reaches_operator": name in operator_text,
                "size_bytes": _size(folder),
            })
    return records
```

- [ ] **Step 4: Run the tests and make them pass**

Run: `python3 -m pytest .claude/tools/census/test_enumerate.py -v`
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add .claude/tools/census/enumerate.py .claude/tools/census/test_enumerate.py
git commit -m "add feature — the artefact census walker, adding .claude/tools/census/enumerate.py"
```

---

### Task 2: The codebook, split mechanical from judgement

**Files:**
- Create: `.claude/tools/census/codebook.py`
- Test: `.claude/tools/census/test_codebook.py`

**Interfaces:**
- Consumes: `enumerate_artefacts` records from Task 1.
- Produces: `QUESTIONS: list[Question]` where `Question = {id, text, kind, answer_fn|None}`, and `answer_mechanical(record) -> dict[str, str]`.

The fourteen questions, and this list does not grow:

| id | question | kind |
| --- | --- | --- |
| `q01_parses` | Does the file parse as valid JSON? | mechanical |
| `q02_folder_name` | Does the folder name match the record's own `name`? | mechanical |
| `q03_is_standard` | Is `is_standard` set, so migrate will import it? | mechanical |
| `q04_module` | Does `module` name a module this app actually declares? | mechanical |
| `q05_referenced` | Is it named by any workspace JSON? | mechanical |
| `q06_reaches_operator` | Is it named by a workspace an operator opens — Back Engines excluded? | mechanical |
| `q07_duplicate_shape` | Does another artefact of the same kind have the same source DocType and the same aggregate? | mechanical |
| `q08_translated` | Does every user-visible label appear in `translations/ar.csv`? | mechanical |
| `q09_needed` | Would an operator notice if this were deleted tomorrow? | judgement |
| `q10_burden` | Does it cost more to maintain than the answer it gives is worth? | judgement |
| `q11_structure` | Is it the right primitive for what it does, or should it be a different one? | judgement |
| `q12_name_truthful` | Does the name describe what it actually shows, or what it was once meant to show? | judgement |
| `q13_name_consistent` | Does the name follow the convention its siblings of the same kind use? | judgement |
| `q14_overlap` | Does another artefact answer the same operator question? | judgement |

- [ ] **Step 1: Write the failing test**

```python
def test_the_codebook_is_fourteen_and_classified():
    assert len(QUESTIONS) == 14
    assert {q["kind"] for q in QUESTIONS} == {"mechanical", "judgement"}
    assert sum(1 for q in QUESTIONS if q["kind"] == "mechanical") == 8

def test_every_mechanical_question_has_an_answer_function():
    for q in QUESTIONS:
        if q["kind"] == "mechanical":
            assert callable(q["answer_fn"]), q["id"]
        else:
            assert q["answer_fn"] is None, q["id"]
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python3 -m pytest .claude/tools/census/test_codebook.py -v`
Expected: FAIL with `ImportError: cannot import name 'QUESTIONS'`.

- [ ] **Step 3: Implement the codebook**

```python
QUESTIONS = [
    {"id": "q01_parses", "text": "Does the file parse as valid JSON?",
     "kind": "mechanical", "answer_fn": lambda r: "yes" if r["parses"] else "no"},
    {"id": "q06_reaches_operator",
     "text": "Is it named by a workspace an operator opens, Back Engines excluded?",
     "kind": "mechanical", "answer_fn": lambda r: "yes" if r["reaches_operator"] else "no"},
    {"id": "q09_needed",
     "text": "Would an operator notice if this were deleted tomorrow?",
     "kind": "judgement", "answer_fn": None},
    # ... the remaining eleven, same shape
]

def answer_mechanical(record):
    return {q["id"]: q["answer_fn"](record) for q in QUESTIONS if q["kind"] == "mechanical"}
```

- [ ] **Step 4: Run the tests and make them pass**

Run: `python3 -m pytest .claude/tools/census/test_codebook.py -v`
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add .claude/tools/census/codebook.py .claude/tools/census/test_codebook.py
git commit -m "add feature — the census codebook and its mechanical answers, adding .claude/tools/census/codebook.py"
```

---

### Task 3: Run the mechanical pass and cut the population

**Files:**
- Modify: none — this task produces a scratchpad artefact only.

- [ ] **Step 1: Answer the eight mechanical questions for all 370 artefacts**

```bash
python3 -c "
from importlib import import_module
import json, sys
sys.path.insert(0, '.claude/tools/census')
e = import_module('enumerate'); c = import_module('codebook')
records = e.enumerate_artefacts('apex')
for r in records: r['mechanical'] = c.answer_mechanical(r)
json.dump(records, open('.claude/audits/census-mechanical.json', 'w'), indent=1)
print('graded', len(records))
"
```
Expected: `graded 370`.

- [ ] **Step 2: Print what the mechanical pass already decided**

```bash
python3 -c "
import json, collections
rs = json.load(open('.claude/audits/census-mechanical.json'))
for q in ('q01_parses','q02_folder_name','q05_referenced','q06_reaches_operator'):
    print(q, dict(collections.Counter(r['mechanical'][q] for r in rs)))
"
```
Expected: `q06_reaches_operator` returns `no` for all 46 dashboard charts and 54 of the 113 number cards. **Those 100 artefacts have their `q09_needed` answer already** — nobody sees them — so they go to the report as a finding, not to an agent.

- [ ] **Step 3: Write the residue slices**

```bash
python3 -c "
import json, os
rs = json.load(open('.claude/audits/census-mechanical.json'))
residue = [r for r in rs if r['mechanical']['q06_reaches_operator'] == 'yes']
groups = [residue[i::12] for i in range(12)]
os.makedirs('.claude/audits/slices', exist_ok=True)
for i, g in enumerate(groups, 1):
    json.dump(g, open(f'.claude/audits/slices/slice{i}.json','w'), indent=1)
print('residue', len(residue), 'slices', [len(g) for g in groups])
"
```
Expected: roughly 270 artefacts across 12 slices of ~22 each. Twelve, not sixteen — the cap is a ceiling and four slots stay free for the verify pass.

- [ ] **Step 4: Plant the canary**

Append one artefact to `slice1.json` that is known-bad and is NOT in the app: a number card named `_Canary Card` whose `source DocType` does not exist. Record its name in `.claude/audits/census-canary.txt`. Task 5 requires it to be caught.

- [ ] **Step 5: Commit the mechanical result**

```bash
git add .claude/audits/census-mechanical.json
git commit -m "add feature — the mechanical half of the artefact census, adding .claude/audits/census-mechanical.json"
```

---

### Task 4: The judgement fan-out

**Files:**
- Create: `.claude/audits/verdicts/slice<N>.json` — one per agent.

**Interfaces:**
- Consumes: `.claude/audits/slices/slice<N>.json` from Task 3.
- Produces: per artefact, `{name, kind, q09_needed, q10_burden, q11_structure, q12_name_truthful, q13_name_consistent, q14_overlap, evidence}` where every answer is one of `yes|no|unsure` and `evidence` cites a `file:line` or a workspace path.

- [ ] **Step 1: Dispatch twelve agents, each with its slice interpolated into the brief**

Each brief must carry, verbatim: the artefact list (names and paths, not a rule for computing them), the six judgement questions with their exact text, the demand that every `no` cites a `file:line`, and the instruction that `unsure` is a valid answer that costs nothing while a guessed `yes` poisons the aggregate.

- [ ] **Step 2: Assert the join before reading any verdict**

```bash
python3 .claude/tools/census/aggregate.py --check-only
```
Expected: `expected 270, distinct 270, duplicated 0, unopened 0`. Any `unopened > 0` voids the run — re-dispatch the missing slice, do not proceed.

- [ ] **Step 3: Confirm the canary was caught**

```bash
grep -l "_Canary Card" .claude/audits/verdicts/*.json
```
Expected: slice1's verdict file, with `q09_needed: no`. If the canary was passed as needed, the whole judgement pass is void — the agents are not reading, and the run repeats with a corrected brief.

---

### Task 5: Aggregate, disagree, report

**Files:**
- Create: `.claude/tools/census/aggregate.py`
- Create: `.claude/audits/artefact-census.json`

**Interfaces:**
- Consumes: `census-mechanical.json` and every `verdicts/slice<N>.json`.
- Produces: the report, with `population`, `coverage`, `control`, `by_kind`, `findings`, and `disagreements`.

- [ ] **Step 1: Write the failing test**

```python
def test_the_report_refuses_to_write_with_unopened_items():
    with pytest.raises(SystemExit):
        aggregate(expected=270, verdicts=_verdicts_missing_one())
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python3 -m pytest .claude/tools/census/test_aggregate.py -v`
Expected: FAIL — `aggregate` does not exist.

- [ ] **Step 3: Implement the aggregator, refusing rather than rounding**

```python
def aggregate(expected, verdicts, mechanical, canary_name):
    seen = {v["name"] for v in verdicts}
    if len(seen) != expected:
        raise SystemExit(f"unopened={expected - len(seen)} — the verdict does not cover the population")
    if not any(v["name"] == canary_name and v["q09_needed"] == "no" for v in verdicts):
        raise SystemExit("control MISSING — the canary was not caught, every number below is unproven")
    ...
```

- [ ] **Step 4: Run the tests and make them pass**

Run: `python3 -m pytest .claude/tools/census/test_aggregate.py -v`
Expected: PASS.

- [ ] **Step 5: Produce the report and read the headline**

```bash
python3 .claude/tools/census/aggregate.py --out .claude/audits/artefact-census.json
python3 -c "
import json; d = json.load(open('.claude/audits/artefact-census.json'))
print(d['population'], d['coverage'], d['control'])
print({k: v['unneeded'] for k, v in d['by_kind'].items()})
"
```

- [ ] **Step 6: Commit**

```bash
git add .claude/tools/census/aggregate.py .claude/tools/census/test_aggregate.py .claude/audits/artefact-census.json
git commit -m "add feature — the artefact census report, adding .claude/audits/artefact-census.json"
```

---

### Task 6: Card what the report found

**Files:**
- Modify: the board only.

- [ ] **Step 1: Open one card per finding class, not one per artefact**

A hundred unseen charts is one card, not a hundred. Each card carries the count, the kind, and the report path as evidence.

- [ ] **Step 2: State the disagreements out loud**

Where two lenses answered the same question differently, that is the interesting half of the run. Report the count and the top five, because an artefact that one reader calls essential and another calls burden is the one worth a decision.

- [ ] **Step 3: Delete nothing yet**

The census grades; it does not act. Deletion is a separate change with its own suite run, and the owner decides which findings become deletions.
