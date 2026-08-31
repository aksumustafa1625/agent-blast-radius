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


def _apply_theme(markup: str, theme: str) -> str:
    """Stamp data-theme onto the document's <html> so the PDF theme is fixed.

    A headless engine does not reliably match prefers-color-scheme, so without
    this the dark report a browser showed would flip to light in the PDF. We
    edit whatever document we were handed rather than re-wrapping it, so a file
    written by any version of the CLI still themes correctly.
    """
    import re
    if re.search(r'<html[^>]*\sdata-theme=', markup):
        return re.sub(r'(<html[^>]*?)\sdata-theme="[^"]*"',
                      rf'\1 data-theme="{theme}"', markup, count=1)
    if re.search(r'<html\b', markup):
        return re.sub(r'(<html\b)', rf'\1 data-theme="{theme}"', markup, count=1)
    # A bare fragment (no <html>): the concentric-circle CSS keys off
    # :root[data-theme=...], so put the attribute where it will take effect.
    return f'<!doctype html><html data-theme="{theme}"><meta charset="utf-8">{markup}</html>'


def main() -> None:
    want_open = "--open" in sys.argv
    # Default to the dark theme: it is what the report shows on a dark desktop
    # and what the demo was recorded against. --light overrides.
    theme = "light" if "--light" in sys.argv else "dark"
    argv = [a for a in sys.argv[1:]
            if a not in ("--open", "--light", "--dark")]

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

    # Any Chromium will do - they all take --headless --print-to-pdf. It used to
    # look for Edge and nothing else, so on macOS and Linux, where nobody has
    # "msedge", the tool refused with a message naming a browser that platform
    # does not ship. This is presentation only and cannot change a verdict, but a
    # dead end that blames the wrong thing still costs the reader an hour.
    edge = _find("msedge",
                 r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                 r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")
    if not edge:
        for name, *paths in (
            ("google-chrome",),
            ("google-chrome-stable",),
            ("chromium",),
            ("chromium-browser",),
            ("chrome",),
            ("microsoft-edge",),
            ("Google Chrome",
             "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            ("Microsoft Edge",
             "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
            ("Chromium",
             "/Applications/Chromium.app/Contents/MacOS/Chromium"),
        ):
            edge = _find(name, *paths)
            if edge:
                break
    if not edge:
        raise SystemExit(
            "[FAIL] No headless Chromium found, and the PDF needs one.\n"
            "       Any of these will do: Microsoft Edge, Google Chrome, Chromium.\n"
            "       The .html report beside it is the same document and needs nothing:\n"
            "       open it and print to PDF from the browser.")

    pdf = html.with_suffix(".pdf")

    # Print a THEMED copy, not the file itself: stamping data-theme fixes the
    # PDF's theme (Edge headless would otherwise default to light and flatten a
    # dark report). Written beside the source so relative asset uris still
    # resolve, and removed afterwards.
    themed = _apply_theme(html.read_text(encoding="utf-8"), theme)
    tmp = html.with_name(html.stem + f".__{theme}__.html")
    tmp.write_text(themed, encoding="utf-8")
    try:
        # Edge's GPU/renderer noise on stderr says nothing about the PDF;
        # suppress it so a successful run does not read like a failed one.
        subprocess.run([edge, "--headless", "--disable-gpu", "--no-sandbox",
                        f"--print-to-pdf={pdf.resolve()}", "--no-pdf-header-footer",
                        tmp.resolve().as_uri()],
                       check=True, timeout=120,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        tmp.unlink(missing_ok=True)

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
