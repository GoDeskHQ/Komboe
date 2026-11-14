#!/usr/bin/env python3
"""Android in-app Wi-Fi OTA: feed shape, rebrand hooks, and injection into the pinned tree."""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "mobile/self-update"
EXAMPLE = ROOT / "distribution/android/latest.example.json"
SHA64 = "a" * 64
FEED = "https://downloads.komboe.com/android/latest.json"


def parse_manifest(raw: str, feed_url: str) -> dict:
    obj = json.loads(raw)
    version_name = str(obj.get("versionName", "")).strip()
    if not version_name:
        raise ValueError("versionName is required")
    version_code = int(obj["versionCode"])
    if version_code <= 0:
        raise ValueError("versionCode must be a positive integer")
    apk_url = str(obj.get("apkUrl", "")).strip()
    if not apk_url.lower().startswith("https://"):
        raise ValueError("apkUrl must be https")
    sha256 = str(obj.get("sha256", "")).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise ValueError("sha256 must be 64 hex characters")
    min_sdk = obj.get("minSdk")
    if min_sdk is not None and int(min_sdk) <= 0:
        raise ValueError("minSdk must be a positive integer")
    from urllib.parse import urlparse

    feed = urlparse(feed_url)
    apk = urlparse(apk_url)
    if (feed.scheme or "").lower() != "https":
        raise ValueError("feed URL must be https")
    if (apk.hostname or "").lower() != (feed.hostname or "").lower():
        raise ValueError("apkUrl host must match the feed host")
    return {
        "versionName": version_name,
        "versionCode": version_code,
        "apkUrl": apk_url,
        "sha256": sha256,
        "minSdk": None if min_sdk is None else int(min_sdk),
        "releaseNotes": obj.get("releaseNotes") or None,
    }


def test_example_feed_parses():
    data = json.loads(EXAMPLE.read_text())
    parsed = parse_manifest(EXAMPLE.read_text(), FEED)
    assert parsed["versionName"] == data["versionName"]
    assert parsed["versionCode"] == data["versionCode"]
    assert parsed["apkUrl"].startswith("https://downloads.komboe.com/android/")
    assert re.fullmatch(r"[0-9a-f]{64}", parsed["sha256"])


def test_rejects_bad_feeds():
    good = {
        "versionName": "2026.11.1",
        "versionCode": 2026110101,
        "apkUrl": "https://downloads.komboe.com/android/app.apk",
        "sha256": SHA64,
    }
    def fails(obj=None, feed=FEED, **overrides):
        payload = dict(good if obj is None else obj)
        payload.update(overrides)
        try:
            parse_manifest(json.dumps(payload), feed)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return
        raise AssertionError(f"expected failure for {overrides or feed}")

    fails(apkUrl="http://downloads.komboe.com/android/app.apk")
    fails(sha256="deadbeef")
    fails(versionCode=0)
    fails(versionName="  ")
    fails(apkUrl="https://evil.example/app.apk")
    fails(feed="http://downloads.komboe.com/android/latest.json")


def test_overlay_and_docs_present():
    for name in (
        "KomboeSelfUpdate.kt",
        "KomboeSelfUpdateManifest.kt",
        "KomboeSelfUpdateReceiver.kt",
        "komboe_update_strings.xml",
    ):
        path = OVERLAY / name
        assert path.is_file(), path
    kotlin = (OVERLAY / "KomboeSelfUpdate.kt").read_text()
    assert "REQUEST_INSTALL_PACKAGES" not in kotlin  # permission lives in the manifest hook
    assert "PackageInstaller" in kotlin
    assert "TRANSPORT_WIFI" in kotlin
    assert "sha256" in (OVERLAY / "KomboeSelfUpdateManifest.kt").read_text()
    strings = (OVERLAY / "komboe_update_strings.xml").read_text()
    assert "https://downloads.komboe.com/android/latest.json" in strings
    running = (ROOT / "docs/RUNNING.md").read_text()
    assert "downloads.komboe.com/android" in running
    e2e = (ROOT / "mobile/ANDROID-E2E.md").read_text()
    assert "Check for updates" in e2e
    compose = (ROOT / "docker-compose.yml").read_text()
    assert "SMTP_FROM: donotreply@komboe.com" in compose


def test_injects_into_pinned_tree_snippets():
    # Use the real files from the pinned checkout when present, otherwise skip the live hook test
    # still always run against a copied snippet tree built from those files if they exist.
    pin_src = Path("/workspace/up/bw-android")
    required = [
        "app/src/main/AndroidManifest.xml",
        "app/src/main/kotlin/com/x8bit/bitwarden/BitwardenApplication.kt",
        "app/src/main/kotlin/com/x8bit/bitwarden/ui/platform/feature/settings/about/AboutScreen.kt",
    ]
    if not all((pin_src / rel).is_file() for rel in required):
        print("inject snippet test skipped (pinned android tree not on this machine)")
        return
    spec = importlib.util.spec_from_file_location(
        "android_rebrand", ROOT / "mobile/android_rebrand.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp)
        for rel in required:
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(pin_src / rel, target)
        mod.inject_self_update(str(dest), str(ROOT))
        manifest = (dest / "app/src/main/AndroidManifest.xml").read_text()
        assert "android.permission.REQUEST_INSTALL_PACKAGES" in manifest
        assert "io.komboe.android.update.KomboeSelfUpdateReceiver" in manifest
        about = (
            dest
            / "app/src/main/kotlin/com/x8bit/bitwarden/ui/platform/feature/settings/about/AboutScreen.kt"
        ).read_text()
        assert "KomboeCheckForUpdatesRow" in about
        assert "komboe_check_for_updates" in about
        app = (
            dest
            / "app/src/main/kotlin/com/x8bit/bitwarden/BitwardenApplication.kt"
        ).read_text()
        assert "KomboeSelfUpdate.schedulePeriodic" in app
        copied = dest / "app/src/main/kotlin/io/komboe/android/update/KomboeSelfUpdate.kt"
        assert copied.is_file()
        # idempotent
        mod.inject_self_update(str(dest), str(ROOT))
        assert "REQUEST_INSTALL_PACKAGES" in (dest / "app/src/main/AndroidManifest.xml").read_text()


def main():
    test_example_feed_parses()
    test_rejects_bad_feeds()
    test_overlay_and_docs_present()
    test_injects_into_pinned_tree_snippets()
    print("ANDROID SELF-UPDATE PASS")


if __name__ == "__main__":
    main()
