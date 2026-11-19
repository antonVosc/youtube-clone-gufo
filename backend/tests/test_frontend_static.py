import re
from pathlib import Path

FRONT = Path(__file__).resolve().parents[2] / "frontend"
FORBIDDEN = [
    "innerHTML",
    "outerHTML",
    "insertAdjacentHTML",
    "document.write",
    "eval(",
    "new Function",
]


def _sources():
    return [p for p in FRONT.glob("*.js")]


def test_frontend_has_sources():
    assert _sources() and (FRONT / "index.html").exists()


def test_no_dangerous_dom_apis():
    for p in _sources():
        code = p.read_text()

        for bad in FORBIDDEN:
            assert bad not in code, f"{p.name} uses {bad}"


def test_index_has_no_inline_scripts_or_handlers():
    html = (FRONT / "index.html").read_text()

    assert not re.search(
        r"<script(?![^>]*\bsrc=)[^>]*>", html
    ), "inline <script> запрещен CSP"
    assert not re.search(r"\son\w+\s*=", html), "inline-обработчики запрещены CSP"
