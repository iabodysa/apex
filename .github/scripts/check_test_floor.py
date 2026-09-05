# Copyright (c) 2026, AFMCO and contributors

import re
import sys

# Floor: the standing baseline is 961. Raise this only after a run whose own
# "Ran N tests" count justifies the new number — never to silence a red run.
MINIMUM_TEST_COUNT = 719

RAN_LINE = re.compile(r"^Ran (\d+) tests? in", re.MULTILINE)


def observed_count(log_text):
    match = RAN_LINE.search(log_text)
    return int(match.group(1)) if match else None


def main(argv):
    with open(argv[1], encoding="utf-8", errors="replace") as handle:
        log_text = handle.read()

    count = observed_count(log_text)
    if count is None:
        print(
            "TEST FLOOR BREACH: no 'Ran N tests' line in the run's output — "
            "the runner died before it counted anything, which is what a setup "
            f"death looks like; observed=absent floor={MINIMUM_TEST_COUNT}"
        )
        return 1
    if count < MINIMUM_TEST_COUNT:
        print(
            f"TEST FLOOR BREACH: observed={count} floor={MINIMUM_TEST_COUNT} — "
            "a setup death also yields a low or zero count, so this reads as a "
            "broken run, not a clean one"
        )
        return 1
    print(f"test count floor satisfied: observed={count} floor={MINIMUM_TEST_COUNT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
