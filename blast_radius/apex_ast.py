"""Bridge to the Node/ANTLR Apex AST extractor (ast_extract.js).

Runs the real parse-tree extractor as a subprocess and returns its IR dict. If
Node or the parser package is not present, or parsing fails, the caller falls
back to the regex extractor - so the tool degrades honestly, never silently
producing wrong results.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(_HERE, "ast_extract.js")
_NODE_MODULES = os.path.join(_HERE, "node_modules", "@apexdevtools", "apex-parser")

# Allow overriding the node binary (e.g. in CI); default resolves from PATH.
_NODE = os.environ.get("BLAST_RADIUS_NODE") or shutil.which("node")

_available_cache: Optional[bool] = None
_parser_version_cache: Optional[str] = None


def parser_version() -> Optional[str]:
    """Version of the ANTLR apex-parser package, or None if it isn't installed.

    The fingerprint binds it because the parse tree IS part of the analysis: a
    parser upgrade can change which reads the AST backend sees (this session's
    differential found one such blind spot), and two runs that saw different reads
    must not be able to share a fingerprint."""
    global _parser_version_cache
    if _parser_version_cache is not None:
        return _parser_version_cache or None
    try:
        with open(os.path.join(_NODE_MODULES, "package.json"), encoding="utf-8") as f:
            _parser_version_cache = json.load(f).get("version") or ""
    except (OSError, ValueError):
        _parser_version_cache = ""
    return _parser_version_cache or None


def ast_available() -> bool:
    """True if the AST backend can actually run: script + parser package present
    AND the node binary genuinely launches (verified once, cached). Probing node
    for real - not just checking a path - keeps the reported backend honest."""
    global _available_cache
    if _available_cache is not None:
        return _available_cache
    _available_cache = False
    if _NODE and os.path.exists(_SCRIPT) and os.path.isdir(_NODE_MODULES):
        try:
            r = subprocess.run([_NODE, "--version"], capture_output=True,
                               text=True, timeout=10)
            _available_cache = r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            _available_cache = False
    return _available_cache


def extract_ir(cls_path: str, timeout: float = 30.0) -> dict:
    """Return the AST IR for one .cls file. Raises on any failure (missing node,
    parser package, parse error, timeout) so the caller can fall back."""
    if not ast_available():
        raise RuntimeError("AST backend unavailable (node or apex-parser missing)")
    # cwd is _HERE so node resolves node_modules; pass an absolute path so a
    # relative cls_path (from the caller's cwd) still resolves.
    res = subprocess.run(
        [_NODE, _SCRIPT, os.path.abspath(cls_path)], cwd=_HERE, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if not res.stdout.strip():
        raise RuntimeError(f"AST extractor produced no output: {res.stderr.strip()}")
    data = json.loads(res.stdout)
    if "error" in data:
        raise RuntimeError(f"AST parse failed: {data['error']}")
    return data
