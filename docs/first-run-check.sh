#!/usr/bin/env bash
# The macOS/Linux tab, checked end to end.
#
#     bash docs/first-run-check.sh
#
# Everything here needs no Salesforce org and no local checkout: it clones what
# the published command clones. Run it on any POSIX machine to answer the
# questions a Windows run cannot - does the published command work there, does a
# fresh clone compute the digest this project publishes, and does the tool fail
# honestly when the Salesforce CLI is absent rather than throwing a traceback.
#
# It needs the repository to be PUBLIC. Against a private repo, git sits waiting
# for a credential prompt and this script hangs with no output at all - which
# cost thirty minutes the first time.
#
# Everything here needs no Salesforce org. It answers the questions a Windows
# machine cannot: does the published POSIX command work, does a fresh clone on
# Linux compute the SAME analyzer digest the project claims, and does the tool
# fail honestly when the CLI is absent rather than throwing a traceback.
set -u

PASS=0; FAIL=0
ok(){ printf "  [ OK ] %s\n" "$1"; PASS=$((PASS+1)); }
no(){ printf "  [FAIL] %s\n" "$1"; FAIL=$((FAIL+1)); }
hd(){ printf "\n== %s\n" "$1"; }

EXPECT_DIGEST="257203d65b68"

hd "environment"
echo "  $(uname -srm)"
echo "  $(python3 --version 2>&1)  at $(command -v python3 || echo MISSING)"
echo "  $(git --version 2>&1)"
command -v python3 >/dev/null && ok "python3 exists (the macOS/Linux tab calls it)" \
                              || no "python3 missing - the published command cannot run"
command -v python >/dev/null && echo "  note: 'python' also exists here" \
                             || echo "  note: 'python' does NOT exist - which is why the tab says python3"

hd "the published clone command, verbatim"
# The published command, exactly as the macOS/Linux tab prints it.
rm -rf ~/agent-blast-radius
GIT_TERMINAL_PROMPT=0 git clone --branch v1.0.0 --depth 1   https://github.com/aksumustafa1625/agent-blast-radius ~/agent-blast-radius 2>/tmp/clone.err
if [ -f ~/agent-blast-radius/measure.py ]; then
  ok "clone at the tag, measure.py present"
else
  no "clone did not produce measure.py"; sed 's/^/        /' /tmp/clone.err
fi
if grep -qi "warning" /tmp/clone.err; then
  no "git printed a warning a stranger would see:"; sed 's/^/        /' /tmp/clone.err
else
  ok "git printed no warning"
fi
cd ~/agent-blast-radius || exit 1

hd "the analyzer digest a fresh clone computes"
D=$(python3 -c "import sys;sys.path.insert(0,'blast_radius');from report import analyzer_version;print(analyzer_version())" 2>&1)
if [ "$D" = "$EXPECT_DIGEST" ]; then
  ok "digest $D matches what the project publishes"
else
  no "digest is $D, the project publishes $EXPECT_DIGEST"
fi

hd "line endings (the CRLF class of bug, from the other side)"
if git ls-files --eol | grep -v "w/lf" | grep -q "w/crlf"; then
  no "some files checked out CRLF on Linux"; git ls-files --eol | grep "w/crlf" | head -5 | sed 's/^/        /'
else
  ok "every file checked out LF"
fi

hd "the suite, the benchmark, the mutation score"
python3 -m unittest discover -s blast_radius -p "test_*.py" >/tmp/t.log 2>&1 \
  && ok "$(tail -3 /tmp/t.log | head -1)" || { no "unit tests failed"; tail -20 /tmp/t.log | sed 's/^/        /'; }
python3 blast_radius/benchmark/run.py >/tmp/b.log 2>&1 \
  && ok "$(grep -m1 'cases:' /tmp/b.log)" || { no "benchmark failed"; tail -12 /tmp/b.log | sed 's/^/        /'; }
python3 blast_radius/benchmark/mutate.py >/tmp/m.log 2>&1 \
  && ok "$(grep -m1 -i 'mutation score' /tmp/m.log)" || { no "mutation run failed"; tail -12 /tmp/m.log | sed 's/^/        /'; }

hd "measure.py with no Salesforce CLI - it must fail HONESTLY"
OUT=$(python3 measure.py 2>&1); RC=$?
echo "$OUT" | sed 's/^/        /'
if echo "$OUT" | grep -qi "Traceback"; then
  no "it threw a traceback instead of explaining"
elif echo "$OUT" | grep -qi "Salesforce CLI is not on PATH"; then
  ok "named the missing prerequisite, exit $RC"
else
  no "unexpected output, exit $RC"
fi

hd "argument handling"
python3 measure.py --nonsense 2>&1 | grep -q "does not take" \
  && ok "an unknown argument is refused, not ignored" || no "an unknown argument was not refused"

hd "the file:// URI this platform gets"
python3 -c "
import pathlib
p = pathlib.Path.home() / 'agent-blast-radius' / 'reports' / 'r.html'
u = p.as_uri()
print('        ' + u)
raise SystemExit(0 if u.startswith('file:///') and '////' not in u else 1)" \
  && ok "well-formed (three slashes, not four)" || no "malformed file URI"

printf "\n==============================\n  PASS %d   FAIL %d\n" "$PASS" "$FAIL"
exit $((FAIL > 0))
