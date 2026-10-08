"""Render public/og-inskect.png, the link preview image, from og-image.svg next to this file.

    uv run --no-project --with fonttools --with resvg-py python scripts/og-image/render.py

It fetches the site's fonts (Barlow Condensed, IBM Plex Sans, IBM Plex Mono) from Google Fonts into a temporary folder,
so the image looks the same on any machine, whatever fonts it has. Rename the PNG when it changes
(and its path in app/app.config.ts and nuxt.config.ts): it's cached for a year.
"""

from __future__ import annotations

import re
import tempfile
import urllib.request
from pathlib import Path

import resvg_py
from fontTools.ttLib import TTFont

HERE = Path(__file__).resolve().parent
OUTPUT = HERE.parent.parent / "public" / "og-inskect.png"
FONTS_CSS = "https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700&family=IBM+Plex+Sans:wght@400&family=IBM+Plex+Mono:wght@500"
# An old browser, so Google Fonts serves WOFF files fontTools reads without brotli.
USER_AGENT = "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/534.30 (KHTML, like Gecko) Safari/534.30"


def _get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=30) as response:
        return response.read()


def main() -> None:
    css = _get(FONTS_CSS).decode()
    with tempfile.TemporaryDirectory() as fonts:
        # Every subset of each weight, so any character the image uses has its glyph.
        for i, url in enumerate(re.findall(r"url\((https://[^)]+)\)", css)):
            woff = Path(fonts) / f"{i}.woff"
            woff.write_bytes(_get(url))
            font = TTFont(woff)
            font.flavor = None
            font.save(Path(fonts) / f"{i}.ttf")
            woff.unlink()
        png = resvg_py.svg_to_bytes(svg_path=str(HERE / "og-image.svg"), font_dirs=[fonts], skip_system_fonts=True)
    OUTPUT.write_bytes(bytes(png))
    print(f"wrote {OUTPUT.relative_to(HERE.parent.parent)}")


if __name__ == "__main__":
    main()
