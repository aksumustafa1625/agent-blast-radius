# -*- coding: utf-8 -*-
"""The analyzer digest must be the same number a clone computes.

This test exists because it was not, for an unknown number of days, and nothing
caught it.

`analyzer_version()` is a sha256 over the bytes of the analysis sources. It seals
every report fingerprint and it is what the footer means by "a verdict is only
reproducible against the tool that produced it". On Windows, `core.autocrlf` and
a text editor that writes `\r\n` are enough to change those bytes without
changing a single character of code - and the digest moves with them.

That happened here. Two analysis sources sat CRLF in the working tree while the
index and every clone held them LF, so the digest published on the specification
page, in FACTS.md and inside both published reports was the digest of a state
that existed on exactly one machine. It was found by a reader running the tool
from a fresh clone and getting a different number in the footer.

The guard is not "remember to normalise". It is this: the sources the digest
covers must contain no CR, so the working tree cannot disagree with the index.
`.gitattributes` already declares `* text=auto eol=lf`; this asserts the file on
disk actually obeys it.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import report  # noqa: E402


class DigestSourcesAreLfOnly(unittest.TestCase):
    """Every file the digest hashes must be byte-identical to its committed form."""

    def test_no_carriage_returns_in_analysis_sources(self):
        here = os.path.dirname(os.path.abspath(report.__file__))
        offenders = []
        for name in report._ANALYSIS_SOURCES:
            path = os.path.join(here, name)
            if not os.path.exists(path):
                continue                     # a missing source is its own failure elsewhere
            with open(path, "rb") as f:
                if b"\r\n" in f.read():
                    offenders.append(name)
        self.assertEqual(
            offenders, [],
            "These analysis sources contain CRLF in the working tree while the "
            "repository stores them LF, so analyzer_version() here does not match "
            "what a clone computes - and every fingerprint sealed with it is "
            "unreproducible:\n  " + "\n  ".join(offenders) +
            "\n\nFix: git add --renormalize . (content does not change, only eol)")

    def test_digest_is_the_published_twelve_hex_form(self):
        """analyzer_version() already returns the 12-character form.

        Asserted because every caller and every document writes it as
        `analyzer_version()[:12]`, which is a no-op that reads as a truncation -
        so a future change to return the full 64 would silently widen the digest
        printed on every report while every caller kept slicing it back.
        """
        d = report.analyzer_version()
        self.assertEqual(len(d), 12)
        self.assertTrue(all(c in "0123456789abcdef" for c in d))


class EntryPointsParse(unittest.TestCase):
    """The files a reader runs first must at least compile.

    Added after a syntax error in cli.py survived a green suite: no test imports
    the entry points, so `python -m unittest` said OK while `python measure.py`
    could not start. The tests covered the analysis and left the front door
    untested - which is the half a stranger meets.
    """

    def test_entry_points_compile(self):
        import ast
        here = os.path.dirname(os.path.abspath(report.__file__))
        root = os.path.dirname(here)
        for path in (os.path.join(here, "cli.py"),
                     os.path.join(here, "org_census.py"),
                     os.path.join(here, "verify_deterministic.py"),
                     os.path.join(root, "measure.py")):
            if not os.path.exists(path):
                continue
            with self.subTest(entry=os.path.basename(path)):
                src = open(path, encoding="utf-8").read()
                try:
                    ast.parse(src, filename=path)
                except SyntaxError as e:
                    self.fail(f"{os.path.basename(path)} does not parse: "
                              f"line {e.lineno}: {e.msg}")


if __name__ == "__main__":
    unittest.main()


class OutputDirectoryTest(unittest.TestCase):
    """--out must work when its directory does not exist yet.

    Every other test in this suite writes into a tmpdir the test itself created,
    so none of them could see the defect this covers: in a fresh clone `reports/`
    does not exist - it is gitignored in full and git carries no empty directories
    - and the published one-command path died there with FileNotFoundError, after
    two minutes of analysis that had already succeeded.

    310 green tests did not catch it. A stranger running the published command
    did, on the first try.
    """

    def test_creates_a_missing_output_directory(self):
        import cli
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "reports", "Org_Agent")
            cli.ensure_outdir(out)
            with open(out + ".md", "w", encoding="utf-8") as f:
                f.write("x")
            self.assertTrue(os.path.exists(out + ".md"))

    def test_creates_nested_directories(self):
        # --out takes any path, so one level is not the general case.
        import cli
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "a", "b", "c", "report")
            cli.ensure_outdir(out)
            self.assertTrue(os.path.isdir(os.path.join(d, "a", "b", "c")))

    def test_existing_directory_is_left_alone(self):
        # Re-running a measurement must not fail on the second run.
        import cli
        with tempfile.TemporaryDirectory() as d:
            cli.ensure_outdir(os.path.join(d, "r", "x"))
            cli.ensure_outdir(os.path.join(d, "r", "x"))   # no exception

    def test_bare_filename_has_a_parent(self):
        # `--out report` has no dirname at all; abspath is what makes it one.
        import cli
        cli.ensure_outdir("report")     # the cwd, which exists - must not throw


class CliHelpersSmokeTest(unittest.TestCase):
    """Call every cli.py reach helper, because only the live path does.

    A NameError in `_record_modes` shipped through 317 tests, the benchmark and
    the mutation run. Nothing reached it: it is behind `--include-counts`, which
    needs an org, so the whole suite was blind to a function that could not run.
    These do not assert verdicts - the analyzer's own tests do that. They assert
    the functions execute, which is the part nothing else checked.
    """

    class _Action:
        def __init__(self, target, target_type="apex"):
            self.target = target
            self.target_type = target_type
            self.name = target

    class _Agent:
        def __init__(self, actions):
            self.actions = actions

    BODY = ("public without sharing class Act {\n"
            "  public static void go() {\n"
            "    List<Acc__c> a = [SELECT Id, Secret__c FROM Acc__c];\n"
            "  }\n"
            "}\n")

    def _root(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        classes = os.path.join(d, "classes")
        os.makedirs(classes)
        with open(os.path.join(classes, "Act.cls"), "w", encoding="utf-8") as f:
            f.write(self.BODY)
        with open(os.path.join(classes, "Act.cls-meta.xml"), "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>'
                    '<ApexClass xmlns="http://soap.sforce.com/2006/04/metadata">'
                    "<apiVersion>58.0</apiVersion><status>Active</status></ApexClass>")
        return d

    def _agent(self):
        return self._Agent([self._Action("Act")])

    def test_reached_objects_runs_both_with_and_without_an_allowlist(self):
        import cli
        d, a = self._root(), self._agent()
        self.assertIn("Acc__c", cli._reached_objects(a, d, backend="regex"))
        self.assertIn("Acc__c", cli._reached_objects(a, d, backend="regex",
                                                     allowed={"Act"}))

    def test_reached_fields_runs(self):
        import cli
        d, a = self._root(), self._agent()
        self.assertTrue(cli._reached_fields(a, d, backend="regex", allowed={"Act"}))

    def test_record_modes_runs(self):
        # The one behind --include-counts, and the one that was broken.
        import cli
        d, a = self._root(), self._agent()
        modes = cli._record_modes(a, d, backend="regex", allowed={"Act"})
        self.assertEqual(modes.get("Acc__c"), "system")   # v58, without sharing


class TrackedPathLengthTest(unittest.TestCase):
    """No tracked path may be long enough to break `git clone` on stock Windows.

    Windows caps a path at 260 unless LongPathsEnabled is set, and it is off by
    default; Git for Windows likewise defaults core.longpaths to false. The
    deepest tracked path here was 189 characters, which made the published clone
    command fail its checkout for anyone whose parent directory was longer than
    about fifty characters - and leave a directory holding only .git, so the
    obvious retry refused too.

    It was fixed once and a `git add -A` after the next live run put it straight
    back within the hour, because a retrieve writes those paths again. A rule in
    .gitignore is the mechanism; this is the alarm for when the rule is wrong.

    160 leaves room for a clone parent of roughly eighty characters, which covers
    a OneDrive-shaped home directory with a company name in it.
    """

    LIMIT = 160

    def test_no_tracked_path_is_long_enough_to_break_a_windows_clone(self):
        import subprocess
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        out = subprocess.run(["git", "ls-files"], cwd=root,
                             capture_output=True, text=True)
        if out.returncode != 0:
            self.skipTest("not a git checkout")
        long = [p for p in out.stdout.splitlines() if len(p) > self.LIMIT]
        self.assertEqual(
            long, [],
            "These tracked paths exceed %d characters, which is what broke "
            "`git clone` on a stock Windows machine:\n  %s"
            % (self.LIMIT, "\n  ".join(f"{len(p)}  {p}" for p in long)))
