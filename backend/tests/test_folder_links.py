from __future__ import annotations

import httpx
import pytest
from skillspector.input_handler import InputHandler

from app.scan_runner import fetch_folder, run_scan

SKILL_MD = "---\nname: pdf\ndescription: fills PDF forms\n---\n# PDF\nRun `python scripts/fill.py`.\n"


def _scan(target: str) -> dict:
    return run_scan(target, use_llm=False, on_step=lambda node: None, on_log=lambda line: None)


def _paths(report: dict) -> list[str]:
    return sorted(component["path"] for component in report["components"])


@pytest.fixture
def gitlab(monkeypatch):
    """Stands in for gitlab.com: a repository whose main branch holds two skills and Git's files."""
    calls: list[tuple] = []

    def resolve_tree_ref(self, repository_url, segments):
        calls.append(("refs", repository_url, segments))
        for end in range(len(segments), 0, -1):
            if "/".join(segments[:end]) in {"main", "feature/x"}:
                return "/".join(segments[:end]), segments[end:]
        raise ValueError("no such ref")

    def clone_git(self, url, *, branch=None):
        calls.append(("clone", url, branch))
        clone = self._get_temp_dir() / "repo"
        for folder in ("skills/pdf", "skills/other"):
            (clone / folder / "scripts").mkdir(parents=True)
            (clone / folder / "SKILL.md").write_text(SKILL_MD)
            (clone / folder / "scripts" / "fill.py").write_text("print('hi')\n")
        (clone / ".git").mkdir()
        (clone / ".git" / "config").write_text("[core]\n")
        return clone

    monkeypatch.setattr(InputHandler, "_resolve_tree_ref", resolve_tree_ref)
    monkeypatch.setattr(InputHandler, "_clone_git", clone_git)
    return calls


def test_a_gitlab_folder_link_scans_only_that_folder(gitlab):
    report = _scan("https://gitlab.com/acme/group/skills/-/tree/feature/x/skills/pdf")

    assert _paths(report) == ["SKILL.md", "scripts/fill.py"]
    # The ref may hold slashes: skillspector's resolution splits it from the folder.
    assert gitlab == [
        ("refs", "https://gitlab.com/acme/group/skills.git", ["feature", "x", "skills", "pdf"]),
        ("clone", "https://gitlab.com/acme/group/skills.git", "feature/x"),
    ]


def test_a_gitlab_folder_of_several_skills_gets_one_verdict_each(gitlab):
    report = _scan("https://gitlab.com/acme/skills/-/tree/main/skills")

    assert [skill["path"] for skill in report["skills"]] == ["other", "pdf"]


def test_git_files_of_a_gitlab_clone_arent_scanned(gitlab):
    report = _scan("https://gitlab.com/acme/skills/-/tree/main")

    assert not any(path.startswith(".git/") for skill in report["skills"] for path in _paths(skill["report"]))


@pytest.mark.parametrize(
    ("target", "message"),
    [
        ("https://gitlab.com/acme/skills/-/tree/nope/skills", "doesn't start with a branch or tag"),
        ("https://gitlab.com/acme/skills/-/tree/main/missing", "isn't a folder at main"),
        ("https://gitlab.com/acme/skills/-/tree/main/skills/../..", "must stay within the repository"),
    ],
)
def test_a_bad_gitlab_folder_link_says_why(gitlab, target, message):
    with pytest.raises(RuntimeError, match=message):
        _scan(target)


@pytest.fixture
def huggingface(monkeypatch):
    """Stands in for huggingface.co: a Space with a skill folder, a weights file in LFS, and a README."""
    files = {
        "skills/pdf/SKILL.md": SKILL_MD,
        "skills/pdf/scripts/fill.py": "print('hi')\n",
        "README.md": "# A Space\n",
    }
    listing = [
        {"type": "directory", "path": "skills/pdf/scripts"},
        {"type": "file", "path": "skills/pdf/SKILL.md", "size": len(SKILL_MD)},
        {"type": "file", "path": "skills/pdf/scripts/fill.py", "size": 12},
        {"type": "file", "path": "skills/pdf/model.bin", "size": 600_000_000, "lfs": {"size": 600_000_000}},
    ]
    requested: list[tuple[str, dict]] = []

    def get(url, **options):
        requested.append((url, options))
        request = httpx.Request("GET", url)
        if url == "https://huggingface.co/api/spaces/acme/demo/tree/main/skills/pdf":
            return httpx.Response(200, json=listing, request=request)
        prefix = "https://huggingface.co/spaces/acme/demo/raw/main/"
        if url.startswith(prefix) and url.removeprefix(prefix) in files:
            return httpx.Response(200, text=files[url.removeprefix(prefix)], request=request)
        return httpx.Response(404, request=request)

    monkeypatch.setattr(httpx, "get", get)
    return listing, requested


def test_a_hugging_face_folder_link_scans_its_files_but_not_lfs_ones(huggingface):
    _, requested = huggingface

    report = _scan("https://huggingface.co/spaces/acme/demo/tree/main/skills/pdf")

    assert _paths(report) == ["SKILL.md", "scripts/fill.py"]
    # Listed recursively, and never a redirect followed.
    assert requested[0][1] == {"params": {"recursive": "true"}, "timeout": 30, "follow_redirects": False}
    assert not any("model.bin" in url for url, _ in requested)


def test_a_hugging_face_folder_too_large_is_refused(huggingface, monkeypatch):
    listing, _ = huggingface
    listing[1]["size"] = 200 * 1024 * 1024

    with pytest.raises(RuntimeError, match="larger than 100 MB"):
        _scan("https://huggingface.co/spaces/acme/demo/tree/main/skills/pdf")


def test_a_missing_hugging_face_folder_says_so(huggingface):
    with pytest.raises(RuntimeError, match="skills/nope isn't in spaces/acme/demo at main"):
        _scan("https://huggingface.co/spaces/acme/demo/tree/main/skills/nope")


@pytest.mark.parametrize(
    "target",
    [
        # skillspector fetches these itself.
        "https://github.com/acme/skills/tree/main/skills/pdf",
        "https://gitlab.com/acme/skills",
        "https://gitlab.com/acme/skills/-/blob/main/SKILL.md",
        "https://huggingface.co/acme/model",
        "https://huggingface.co/acme/model/resolve/main/SKILL.md",
    ],
)
def test_other_targets_are_left_to_skillspector(target, monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: pytest.fail("nothing should be fetched"))
    handler = InputHandler()
    try:
        assert fetch_folder(handler, target, lambda line: None) is None
    finally:
        handler.cleanup()

