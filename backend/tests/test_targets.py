from __future__ import annotations

import pytest

from app.targets import raw_file_url


@pytest.mark.parametrize(
    ("link", "raw"),
    [
        (
            "https://github.com/anthropics/skills/blob/main/skills/pdf/SKILL.md",
            "https://raw.githubusercontent.com/anthropics/skills/main/skills/pdf/SKILL.md",
        ),
        # /raw/ redirects to the same place, and skillspector doesn't follow redirects.
        (
            "https://github.com/acme/skills/raw/v1.2/SKILL.md",
            "https://raw.githubusercontent.com/acme/skills/v1.2/SKILL.md",
        ),
        # A file view's line anchor and query mean nothing to the raw file.
        (
            "https://www.github.com/acme/skills/blob/main/SKILL.md?plain=1#L10",
            "https://raw.githubusercontent.com/acme/skills/main/SKILL.md",
        ),
        # A ref with slashes maps segment for segment.
        (
            "https://github.com/acme/skills/blob/feature/x/SKILL.md",
            "https://raw.githubusercontent.com/acme/skills/feature/x/SKILL.md",
        ),
        (
            "https://gitlab.com/group/sub/project/-/blob/main/skills/SKILL.md",
            "https://gitlab.com/group/sub/project/-/raw/main/skills/SKILL.md",
        ),
        (
            "https://huggingface.co/acme/model/blob/main/SKILL.md",
            "https://huggingface.co/acme/model/resolve/main/SKILL.md",
        ),
        (
            "https://huggingface.co/spaces/acme/demo/blob/main/SKILL.md",
            "https://huggingface.co/spaces/acme/demo/resolve/main/SKILL.md",
        ),
    ],
)
def test_file_views_become_raw_downloads(link, raw):
    assert raw_file_url(link) == raw


@pytest.mark.parametrize(
    "link",
    [
        "https://github.com/acme/skills",
        "https://github.com/acme/skills.git",
        "https://github.com/acme/skills/tree/main/pdf",
        # No file after the ref: nothing to download.
        "https://github.com/acme/skills/blob/main",
        "https://raw.githubusercontent.com/acme/skills/main/SKILL.md",
        "https://github.com/acme/skills/archive/refs/heads/main.zip",
        "https://gitlab.com/group/project",
        "https://huggingface.co/acme/model",
        "https://example.com/blob/main/SKILL.md",
    ],
)
def test_other_links_are_left_alone(link):
    assert raw_file_url(link) == link
