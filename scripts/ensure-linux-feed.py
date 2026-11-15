#!/usr/bin/env python3
"""Write latest-linux.yml next to the AppImage and check that the feed matches the file."""
from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path


def main() -> None:
    dist = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    images = sorted(path for path in dist.glob("*.AppImage") if path.is_file())
    if len(images) != 1:
        raise SystemExit(f"expected one AppImage in {dist}, found {[path.name for path in images]}")
    image = images[0]
    digest = hashlib.sha512()
    with image.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    fingerprint = base64.b64encode(digest.digest()).decode("ascii")
    package = json.loads((dist.parent / "package.json").read_text(encoding="utf-8"))
    version = package["version"]
    text = (
        f"version: {version}\n"
        "files:\n"
        f"  - url: {image.name}\n"
        f"    sha512: {fingerprint}\n"
        f"    size: {image.stat().st_size}\n"
        f"path: {image.name}\n"
        f"sha512: {fingerprint}\n"
    )
    dest = dist / "latest-linux.yml"
    dest.write_text(text, encoding="utf-8")
    written = dest.read_text(encoding="utf-8")
    if fingerprint not in written or f"version: {version}" not in written or image.name not in written:
        raise SystemExit("latest-linux.yml does not match the AppImage")
    print(f"latest-linux.yml {version} {image.name} {fingerprint}")


if __name__ == "__main__":
    main()
