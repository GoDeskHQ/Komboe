#!/usr/bin/env python3
"""Publish Komboe release files onto the komboe.com downloads tree.

Copies an APK (and any other artifacts) into a publish directory, writes
android/latest.json and komboe-downloads.json, and rebuilds the marketing
downloads page. Richard copies the publish directory onto the server volume
mounted at /var/komboe-downloads (URL prefix https://komboe.com/downloads/).

This script does not create DNS records and does not deploy.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts/build-downloads-manifest.py"
SITE = ROOT / "apps/web-marketing"
PUBLIC = "https://komboe.com/downloads/"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apk", type=Path, help="Android APK to publish (io.komboe.android-*.apk or komboe-android.apk)")
    parser.add_argument("--artifacts", type=Path, help="Directory of other already-named artifacts to include")
    parser.add_argument("--publish-dir", type=Path, required=True, help="Output tree Richard copies to /var/komboe-downloads")
    parser.add_argument("--url-prefix", default=PUBLIC)
    parser.add_argument("--version-name", default=None)
    parser.add_argument("--version-code", type=int, default=None)
    parser.add_argument("--min-sdk", type=int, default=29)
    parser.add_argument("--release-notes", default=None)
    parser.add_argument("--released-at", default=None)
    parser.add_argument("--revision", default=None)
    parser.add_argument("--out", type=Path, action="append", help="Where to write komboe-downloads.json (repeatable)")
    parser.add_argument("--rebuild-site", action="store_true", help="Run apps/web-marketing/build.py after updating distribution/")
    args = parser.parse_args()

    staging = args.publish_dir / ".staging-artifacts"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    if args.artifacts and args.artifacts.is_dir():
        for path in args.artifacts.iterdir():
            if path.is_file():
                shutil.copy2(path, staging / path.name)
    apk_dest = None
    if args.apk:
        if not args.apk.is_file():
            raise SystemExit(f"APK not found: {args.apk}")
        name = args.apk.name
        if name == "komboe-android-debug.apk":
            raise SystemExit("refusing to publish komboe-android-debug.apk")
        if args.version_name and not name.startswith("io.komboe.android-"):
            name = f"io.komboe.android-{args.version_name}.apk"
        apk_dest = staging / name
        shutil.copy2(args.apk, apk_dest)

    meta = {
        "versionName": args.version_name,
        "versionCode": args.version_code,
        "minSdk": args.min_sdk,
        "releaseNotes": args.release_notes or (
            "In-app updates now read https://komboe.com/downloads/android/latest.json. "
            "The same APK is listed on the Komboe downloads page."
        ),
    }
    meta_path = staging / "android-meta.json"
    meta_path.write_text(json.dumps({k: v for k, v in meta.items() if v is not None}, indent=2) + "\n")

    publish = args.publish_dir
    publish.mkdir(parents=True, exist_ok=True)
    outs = list(args.out or [])
    dist_manifest = ROOT / "distribution/komboe-downloads.json"
    site_manifest = SITE / "komboe-downloads.json"
    if dist_manifest not in outs:
        outs.append(dist_manifest)
    if site_manifest not in outs:
        outs.append(site_manifest)
    publish_manifest = publish / "komboe-downloads.json"
    if publish_manifest not in outs:
        outs.append(publish_manifest)

    cmd = [
        sys.executable,
        str(BUILDER),
        "--artifacts",
        str(staging),
        "--publish-dir",
        str(publish),
        "--url-prefix",
        args.url_prefix,
        "--android-meta",
        str(meta_path),
    ]
    if args.revision:
        cmd.extend(["--revision", args.revision])
    if args.released_at:
        cmd.extend(["--released-at", args.released_at])
    else:
        cmd.extend(["--released-at", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")])
    for dest in outs:
        cmd.extend(["--out", str(dest)])
    subprocess.check_call(cmd)

    # Do not leave the staging APK or meta inside the publish tree.
    if (publish / ".staging-artifacts").exists():
        shutil.rmtree(publish / ".staging-artifacts")
    shutil.rmtree(staging, ignore_errors=True)

    if args.rebuild_site:
        subprocess.check_call([sys.executable, "build.py"], cwd=SITE, env={**__import__("os").environ, "KOMBOE_ENV": "production"})

    print(f"published tree: {publish}")
    feed = publish / "android" / "latest.json"
    if feed.is_file():
        print(f"android feed: {feed}")
        print(feed.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
