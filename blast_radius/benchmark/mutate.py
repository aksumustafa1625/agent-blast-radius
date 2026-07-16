"""Mutation testing for the Agent Authority Benchmark - does the corpus have teeth?

A benchmark that passes on day one proves nothing on its own: it may just be
agreeing with the implementation it was written next to. So break the analyzer on
purpose, one semantic at a time, and check the benchmark NOTICES.

    caught  = the benchmark failed when the analyzer was broken -> the corpus
              actually constrains that semantic.
    ESCAPED = the analyzer was broken and the benchmark still passed -> a BLIND
              SPOT in the corpus. This is the real output of this file. An escape
              is a finding, not an error.

Run from the repo root:  python blast_radius/benchmark/mutate.py
Exit 1 if any mutation escapes.
"""
from __future__ import annotations

import contextlib
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import apex_introspect            # noqa: E402
import authority_analyzer         # noqa: E402
import run as benchmark           # noqa: E402


def _benchmark_fails() -> bool:
    """Run the benchmark quietly; True if it reports any mismatch."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = benchmark.main([])
    return code != 0


@contextlib.contextmanager
def _patched(module, name, value):
    original = getattr(module, name)
    setattr(module, name, value)
    try:
        yield
    finally:
        setattr(module, name, original)


# Each mutation breaks ONE semantic the tool claims to get right.
def _mut_always_system():
    real = apex_introspect._resolve
    return _patched(apex_introspect, "_resolve",
                    lambda clause, api, sharing: apex_introspect.ResolvedMode(
                        False, False, "MUTANT: always system"))


def _mut_always_user():
    return _patched(apex_introspect, "_resolve",
                    lambda clause, api, sharing: apex_introspect.ResolvedMode(
                        True, True, "MUTANT: always user"))


def _mut_ignore_version():
    """Treat every class as legacy: the exact false positive sfge makes on v67."""
    real = apex_introspect._resolve
    return _patched(apex_introspect, "_resolve",
                    lambda clause, api, sharing: real(clause, 58.0, sharing))


def _mut_no_always_readable():
    """Flag Id/Name/audit fields - a guaranteed false positive on real queries."""
    return _patched(authority_analyzer, "_ALWAYS_READABLE", set())


def _mut_no_sanitizer():
    return _patched(apex_introspect, "_sanitizer", lambda src: None)


def _mut_no_async():
    return _patched(apex_introspect, "_async_handoffs", lambda src: [])


def _mut_no_sosl():
    return _patched(apex_introspect, "_sosl_operations",
                    lambda src, api, sharing: [])


def _mut_dml_always_user():
    return _patched(apex_introspect, "_resolve_dml_fls", lambda mode, api: True)


MUTATIONS = [
    ("precedence: always system mode", _mut_always_system,
     "every v67/USER_MODE case should now cry wolf"),
    ("precedence: always user mode", _mut_always_user,
     "every legacy escalation should now be missed"),
    ("precedence: ignore apiVersion (treat all as v58)", _mut_ignore_version,
     "the v67 secure-by-default cases should now cry wolf - this is sfge's mistake"),
    ("false-positive guard: flag Id/Name/audit fields", _mut_no_always_readable,
     "the Id-only query should now be flagged"),
    ("sanitizer: ignore Security.stripInaccessible", _mut_no_sanitizer,
     "the discarded/wrong-AccessType bugs should go unreported"),
    ("async: ignore EventBus/Queueable/callouts", _mut_no_async,
     "every async hand-off should go unreported"),
    ("reach: ignore SOSL entirely", _mut_no_sosl,
     "the SOSL escalation should be missed - this was a real blind spot once"),
    ("writes: treat all DML as user mode", _mut_dml_always_user,
     "the legacy write escalation should be missed"),
]


def main() -> int:
    print("=" * 74)
    print("BENCHMARK MUTATION TESTING - does the corpus detect a broken analyzer?")
    print("=" * 74)

    # sanity: the benchmark must PASS before we start breaking things
    if _benchmark_fails():
        print("ABORT: the benchmark already fails unmutated - fix that first.")
        return 1

    escaped = []
    for label, mutation, expectation in MUTATIONS:
        with mutation():
            caught = _benchmark_fails()
        mark = "caught " if caught else "ESCAPED"
        print(f"  [{mark}] {label}")
        if not caught:
            print(f"            blind spot: {expectation}")
            escaped.append(label)

    print("-" * 74)
    total = len(MUTATIONS)
    print(f"mutation score: {total - len(escaped)}/{total} caught")
    if escaped:
        print()
        print("ESCAPES ARE FINDINGS - the corpus does not constrain these semantics:")
        for e in escaped:
            print(f"  - {e}")
    print("=" * 74)
    return 1 if escaped else 0


if __name__ == "__main__":
    sys.exit(main())
