# -*- coding: utf-8 -*-
"""Blast Radius HTML report -> PDF. A separate step, never part of the analysis.

The analyzer's HTML is already standalone (styles embedded, zero external
requests — measured), so unlike a markdown report this needs no pandoc: Edge
headless is the whole chain, and Edge ships with Windows.

The PDF is PRESENTATION ONLY. The evidence is the md/html the analyzer wrote
and the fingerprint in its footer; printing does not re-run the analysis and
cannot change a verdict. Rendering it here rather than in cli.py keeps that
boundary where the report's own footer claims it is.

Usage:   python -m blast_radius.make_pdf [ts_run2.html] [--open]
Output:  .pdf with the same name, in the same directory.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def _find(exe: str, *extra: str) -> str | None:
    p = shutil.which(exe)
    if p:
        return p
    for c in extra:
        if Path(c).exists():
            return c
    return None


def main() -> None:
    want_open = "--open" in sys.argv
    argv = [a for a in sys.argv[1:] if a != "--open"]

    html = Path(argv[0]) if argv else None
    if html is None:
        # Newest report in the working directory: the demo's last run is the
        # one you want to show, and its name carries no date to type wrong.
        cands = sorted(Path(".").glob("*.html"), key=lambda p: p.stat().st_mtime)
        if not cands:
            raise SystemExit("[FAIL] No .html report here - run first: "
                             "python -m blast_radius.cli --agent <name> --org <alias>")
        html = cands[-1]
    if not html.exists():
        raise SystemExit(f"[FAIL] Report not found: {html}")

    edge = _find("msedge",
                 r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                 r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")
    if not edge:
        raise SystemExit("[FAIL] Edge not found (headless PDF engine).")

    pdf = html.with_suffix(".pdf")
    # Edge's GPU/renderer noise on stderr says nothing about the PDF; suppress
    # it so a successful run does not read like a failed one.
    subprocess.run([edge, "--headless", "--disable-gpu", "--no-sandbox",
                    f"--print-to-pdf={pdf.resolve()}", "--no-pdf-header-footer",
                    html.resolve().as_uri()],
                   check=True, timeout=120,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Edge can flush the file asynchronously after it exits, so an immediate
    # size check reads a partial file. Wait for the size to stop moving —
    # observed behaviour in the Aktenlage PDF step, not a guess.
    last = -1
    for _ in range(20):
        size = pdf.stat().st_size if pdf.exists() else 0
        if size >= 10_000 and size == last:
            break
        last = size
        time.sleep(0.5)

    if not pdf.exists() or pdf.stat().st_size < 10_000:
        raise SystemExit(f"[FAIL] PDF not produced / suspiciously small: {pdf}")
    print(f"[OK] PDF written -> {pdf.resolve()}  ({pdf.stat().st_size // 1024} KB)")

    if want_open:
        # Opening is a convenience: a PDF the viewer refuses to open is still
        # a produced PDF, so this must not fail the run.
        try:
            os.startfile(pdf)
            print("[OK] Opened in the default PDF viewer.")
        except OSError as e:
            print(f"[!]  PDF is on disk but could not be opened: {e}")


if __name__ == "__main__":
    main()
