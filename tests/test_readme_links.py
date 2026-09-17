"""The README is also the PyPI project description, so it has no repo context.

PyPI renders the README standalone. A repo-relative path resolves against
`pypi.org/project/pyhood/`, which serves the project page for any sub-path,
so a broken link returns HTTP 200 and looks fine to a link checker while
sending the reader nowhere.

This has shipped twice: the logo was a broken image from 0.4.0 until 0.12.1,
and all four migration guide links were dead until 0.12.3. Both were
repo-relative paths that render correctly on GitHub.
"""

import re
from pathlib import Path

import pytest

README = Path(__file__).resolve().parent.parent / "README.md"

# Markdown link or image targets: the text may itself contain a nested
# image link, as badges do, so match the target rather than the pair.
LINK_TARGET = re.compile(r"\]\(([^)]+)\)")
HTML_TARGET = re.compile(r'<(?:img|a)\b[^>]*?(?:src|href)="([^"]+)"')

ALLOWED_PREFIXES = ("https://", "http://", "mailto:", "#")


def targets() -> list[str]:
    text = README.read_text(encoding="utf-8")
    return LINK_TARGET.findall(text) + HTML_TARGET.findall(text)


def test_readme_exists():
    assert README.is_file(), f"{README} not found"


@pytest.mark.parametrize("target", targets())
def test_no_relative_targets(target):
    """Every link and image must be absolute.

    Use the full URL, e.g.
    https://github.com/jamestford/pyhood/blob/main/docs/guide.md
    rather than docs/guide.md, so the link works from the PyPI page too.
    """
    assert target.startswith(ALLOWED_PREFIXES), (
        f"{target!r} is repo-relative and will not resolve on PyPI. "
        f"Use an absolute https:// URL."
    )


def test_there_are_targets_to_check():
    """Guard against the regexes silently matching nothing."""
    assert len(targets()) > 10
