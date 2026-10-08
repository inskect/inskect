"""Scan targets as skillspector should fetch them.

A code host's file link (GitHub's /blob/) is a web page around the file. skillspector downloads it
as a direct file, so without a rewrite it scans the page's HTML instead of the skill. Each link
here becomes the host's raw download of the same file, at the same ref and path.

An MCP server is scanned by its entry in the MCP Registry, named or linked: either becomes the
registry API's URL for that entry, which app/scan_runner.py recognises.
"""

from __future__ import annotations

import re
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from app.scan_runner import MCP_ENTRY_PREFIX, MCP_REGISTRY_HOST

_GITHUB_HOSTS = {"github.com", "www.github.com"}


def raw_file_url(target: str) -> str:
    """The raw download for a file-view link on GitHub, GitLab or Hugging Face; anything else as is.

    The query and fragment of a file view (?plain=1, #L10) mean nothing to the raw file and go.
    """
    parts = urlsplit(target)
    host = (parts.hostname or "").lower()
    segments = parts.path.split("/")[1:]

    if host in _GITHUB_HOSTS:
        # /<owner>/<repo>/blob/<ref>/<path…> → raw.githubusercontent.com/<owner>/<repo>/<ref>/<path…>
        if len(segments) >= 5 and segments[2] in ("blob", "raw") and all(segments[:2]):
            path = "/" + "/".join(segments[:2] + segments[3:])
            return urlunsplit(("https", "raw.githubusercontent.com", path, "", ""))
    elif host == "gitlab.com":
        # /<group…>/<project>/-/blob/<ref>/<path…> → the same with /-/raw/
        for i in range(len(segments) - 3):
            if segments[i] == "-" and segments[i + 1] == "blob" and i >= 2:
                path = "/" + "/".join([*segments[:i], "-", "raw", *segments[i + 2 :]])
                return urlunsplit(("https", host, path, "", ""))
    elif host == "huggingface.co" and "blob" in segments[2:-2]:
        # /[spaces|datasets/]<owner>/<repo>/blob/<ref>/<path…> → the same with /resolve/
        i = segments.index("blob", 2)
        path = "/" + "/".join([*segments[:i], "resolve", *segments[i + 1 :]])
        return urlunsplit(("https", host, path, "", ""))
    return target


# A server's name in the registry: a reverse-DNS namespace, then its own name (the registry's
# server.schema.json), e.g. io.github.acme/weather.
# The namespace always has a dot, which tells a name from a GitHub owner/repo.
_MCP_SERVER_NAME = re.compile(r"^[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+/[a-zA-Z0-9._-]+$")
# The registry API's paths for one server: /v0/servers/<name>[/versions/<version>], in any API version.
_MCP_ENTRY_PATH = re.compile(r"^/v0(?:\.\d+)?/servers/([^/]+)(?:/versions/([^/]+))?/?$")


def mcp_entry_url(target: str) -> str | None:
    """The registry API's URL for an MCP server's entry, from its name or a registry link; else None.

    A name, or a link without a version, means the latest version.
    """
    name, version = target, "latest"
    parts = urlsplit(target)
    if parts.scheme:
        match = _MCP_ENTRY_PATH.match(parts.path) if (parts.hostname or "").lower() == MCP_REGISTRY_HOST else None
        if match is None:
            return None
        name, version = unquote(match.group(1)), unquote(match.group(2) or "latest")
    if not _MCP_SERVER_NAME.match(name):
        return None
    return f"{MCP_ENTRY_PREFIX}{quote(name, safe='')}/versions/{quote(version, safe='')}"
