#!/usr/bin/env python3
"""Fail unless android/latest.json describes the APK bytes sitting next to it.

CI writes both files into the android-fdroid-debug artifact. An empty directory
is a skipped Android build, not a mismatch.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def check(root: Path) -> None:
    apks = sorted(p for p in root.rglob("*.apk") if p.is_file())
    if not apks:
        print(f"no APK under {root}; latest.json check skipped")
        return
    feeds = sorted(p for p in root.rglob("latest.json") if p.is_file())
    if len(feeds) != 1:
        raise SystemExit(f"expected one latest.json next to the APK, found {len(feeds)}")
    apk = apks[0]
    feed = json.loads(feeds[0].read_text(encoding="utf-8"))
    digest = hashlib.sha256(apk.read_bytes()).hexdigest()
    if feed.get("sha256") != digest:
        raise SystemExit(f"latest.json sha256 {feed.get('sha256')} != apk {digest}")
    version_code = int(feed["versionCode"])
    if version_code <= 0:
        raise SystemExit("versionCode must be a positive integer")
    apk_url = str(feed.get("apkUrl") or "")
    if not apk_url.startswith("https://komboe.com/downloads/android/"):
        raise SystemExit(f"apkUrl is not on the main downloads host: {apk_url}")
    if "downloads.komboe.com" in apk_url:
        raise SystemExit("apkUrl must not use a downloads subdomain")
    if Path(apk_url).name != apk.name and apk.name.startswith("io.komboe.android-"):
        raise SystemExit(f"apkUrl filename {Path(apk_url).name} != {apk.name}")
    note = next(root.rglob("android-apk.txt"), None)
    if note is not None:
        text = note.read_text(encoding="utf-8")
        if f"file sha256 {digest}" not in text:
            raise SystemExit("android-apk.txt sha256 does not match the APK")
        if f"versionCode {version_code}" not in text:
            raise SystemExit("android-apk.txt versionCode does not match latest.json")
    print("latest.json matches", apk.name, version_code, digest)


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    check(root)


if __name__ == "__main__":
    main()
