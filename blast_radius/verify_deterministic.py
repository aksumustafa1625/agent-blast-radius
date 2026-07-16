"""Determinism proof: run the analyzer twice with identical inputs and assert the
two reports are byte-for-byte identical with the same fingerprint.

This turns the tool's core claim ("deterministic, not a model's guess") into a
demonstrated fact. Point it at whatever agent you already scan:

    python blast_radius/verify_deterministic.py -- \
        --agent TechnoStore_Revenue_Assistant_v1 \
        --permission-set TechnoStore_Revenue_Assistant2098228049_Permissions \
        --org TechnoStore

Everything after `--` is passed through to cli.py verbatim. Exit 0 = identical.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys


def _run(passthrough, out):
    cmd = [sys.executable, "blast_radius/cli.py", *passthrough,
           "--no-org-health",           # org-health is live-derived and not the subject here
           "--out", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode not in (0, 1):       # 1 is a normal --fail-on gate, not a crash
        sys.stderr.write(r.stdout + r.stderr)
        raise SystemExit(f"cli.py failed (exit {r.returncode})")


def _digest(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main() -> int:
    if "--" in sys.argv:
        passthrough = sys.argv[sys.argv.index("--") + 1:]
    else:
        passthrough = sys.argv[1:]
    if not passthrough:
        raise SystemExit("pass the cli.py args after `--` (e.g. --agent X --org Y ...)")

    _run(passthrough, "_det_a")
    _run(passthrough, "_det_b")

    ok = True
    for ext in ("md", "html"):
        da, db = _digest(f"_det_a.{ext}"), _digest(f"_det_b.{ext}")
        same = da == db
        ok = ok and same
        print(f"  {ext:4} {'IDENTICAL' if same else 'DIFFERENT'}  sha256={da[:16]}...")
    print("=" * 52)
    print("DETERMINISTIC [OK]  two runs produced identical reports" if ok
          else "NON-DETERMINISTIC [FAIL]  reports differ")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
