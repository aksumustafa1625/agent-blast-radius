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
import sys
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


if __name__ == "__main__":
    unittest.main()
