from __future__ import annotations

from pathlib import Path

from app.core.config import Settings

# conftest turns settings files off for every other test; these check that they're read.
ENV_FILES = (".env", ".env.local")


def test_env_local_is_read_and_overrides_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("INSKECT_AUTH=none\nINSKECT_MAX_CONCURRENT_SCANS=3\n")
    (tmp_path / ".env.local").write_text("INSKECT_AUTH=accounts\n")

    settings = Settings(_env_file=ENV_FILES)

    assert settings.auth == "accounts"
    assert settings.max_concurrent_scans == 3


def test_env_local_alone_is_enough(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.local").write_text("INSKECT_AUTH=accounts\n")

    assert Settings(_env_file=ENV_FILES).auth == "accounts"


def test_settings_files_from_older_versions_still_load(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.local").write_text("INSKECT_ADMIN_TOKEN=left-over\nINSKECT_MAX_QUEUED_SCANS=7\n")

    assert Settings(_env_file=ENV_FILES).max_queued_scans == 7


def test_the_example_settings_file_loads_as_the_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    example = Path(__file__).resolve().parents[1] / ".env.example"
    (tmp_path / ".env").write_text(example.read_text())

    settings = Settings(_env_file=ENV_FILES)

    assert settings.auth == "none"
    assert settings.database_url is None
