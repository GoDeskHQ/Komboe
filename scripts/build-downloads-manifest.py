#!/usr/bin/env python3
"""Build komboe-downloads.json from files that actually exist in an artifact directory.

A download URL is present only when the named file was in the artifact directory
and copied to the publish directory. Store listings are not used.

Refused on purpose:
- komboe-android-debug.apk (internal debug filename, not a production release name)
- any URL that is not produced from a file in the artifact directory

When an Android APK is published (komboe-android.apk or io.komboe.android-*.apk),
this script also writes android/latest.json for the in-app updater. The public
origin is https://komboe.com/downloads/ — there is no downloads.komboe.com host.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION_DOCS = "https://github.com/GoDeskio/Komboe/blob/main/docs/BROWSER-EXTENSIONS.md"
SOURCE = "https://github.com/GoDeskio/Komboe"
MOBILE_DOCS = "https://github.com/GoDeskio/Komboe/tree/main/mobile"
PUBLIC_PREFIX = "https://komboe.com/downloads/"

# filename None means there is no artifact name because the platform is not built.
# "prefix" is the directory under the downloads origin (android/, desktop/, …).
CATALOG = [
    {
        "id": "extension-chromium-mv3",
        "filename": "komboe-chrome-mv3.zip",
        "prefix": "",
        "name": "Browser extension (Chromium)",
        "platforms": ["Chrome", "Edge", "Brave", "Opera", "Vivaldi", "Cerebro"],
        "kind": "extension",
        "channel": "unsigned-testing",
        "docsUrl": EXTENSION_DOCS,
        "install": (
            "No extension store listing. Unzip the file and load it unpacked "
            "(chrome://extensions, edge://extensions, or the Chromium equivalent). "
            "The same zip is what Edge, Brave, Opera, Vivaldi, and Cerebro load."
        ),
        "missing": "The clients image has not published komboe-chrome-mv3.zip into this vault.",
    },
    {
        "id": "extension-firefox",
        "filename": "komboe-firefox.zip",
        "prefix": "",
        "name": "Browser extension (Firefox)",
        "platforms": ["Firefox", "Tor Browser"],
        "kind": "extension",
        "channel": "unsigned-testing",
        "docsUrl": EXTENSION_DOCS,
        "install": "No add-ons listing. Load the zip as a temporary add-on from about:debugging.",
        "missing": "No komboe-firefox.zip is in the release artifacts.",
    },
    {
        "id": "extension-safari",
        "filename": "komboe-safari.zip",
        "prefix": "",
        "name": "Browser extension (Safari)",
        "platforms": ["Safari"],
        "kind": "extension",
        "channel": "unavailable",
        "docsUrl": EXTENSION_DOCS,
        "install": "Safari requires a macOS + Xcode build. There is no Linux CI artifact.",
        "missing": "No Safari extension build. A macOS + Xcode build is required and is not set up.",
    },
    {
        "id": "desktop-windows",
        "filename": "komboe-desktop-win-x64-setup.exe",
        "prefix": "desktop/",
        "name": "Desktop for Windows",
        "platforms": ["Windows"],
        "kind": "desktop",
        "channel": "unsigned-testing",
        "docsUrl": SOURCE,
        "install": "Unsigned testing installer. Windows SmartScreen will warn.",
        "missing": "No verified current Windows installer. Older unsigned builds are not offered.",
    },
    {
        "id": "desktop-linux-deb",
        "filename": "komboe-desktop-amd64.deb",
        "prefix": "desktop/",
        "name": "Desktop for Linux (.deb)",
        "platforms": ["Linux"],
        "kind": "desktop",
        "channel": "unsigned-testing",
        "docsUrl": SOURCE,
        "install": "Unsigned testing package. Install with your package manager, then set the Komboe server URL.",
        "missing": "No verified current Linux .deb. Older unsigned builds are not offered.",
    },
    {
        "id": "desktop-linux-appimage",
        "filename": "komboe-desktop-x86_64.AppImage",
        "prefix": "desktop/",
        "name": "Desktop for Linux (AppImage)",
        "platforms": ["Linux"],
        "kind": "desktop",
        "channel": "unsigned-testing",
        "docsUrl": SOURCE,
        "install": "Unsigned testing AppImage. Make it executable and run it, then set the Komboe server URL.",
        "missing": "No verified current Linux AppImage. Older unsigned builds are not offered.",
    },
    {
        "id": "desktop-macos",
        "filename": "komboe-desktop-macos.dmg",
        "prefix": "desktop/",
        "name": "Desktop for macOS",
        "platforms": ["macOS"],
        "kind": "desktop",
        "channel": "unavailable",
        "docsUrl": SOURCE,
        "install": "",
        "missing": "No macOS build. Apple signing and notarization are not set up.",
    },
    {
        "id": "android",
        "filename": "komboe-android.apk",
        "patterns": ["komboe-android.apk", "io.komboe.android-*.apk"],
        "prefix": "android/",
        "name": "Android",
        "platforms": ["Android"],
        "kind": "mobile",
        "channel": "sideload",
        "docsUrl": MOBILE_DOCS,
        "install": (
            "Sideload this APK and allow installs from this source if Android asks. "
            "After the first install, the app checks for updates from this page over "
            "Wi-Fi or mobile data. Settings → About → Check for updates also works. "
            "It is signed with the Komboe debug key, so it upgrades the existing sideload."
        ),
        "missing": "No Android APK has been published to this downloads page yet.",
    },
    {
        "id": "ios",
        "filename": None,
        "prefix": "",
        "name": "iPhone and iPad",
        "platforms": ["iOS"],
        "kind": "mobile",
        "channel": "unavailable",
        "docsUrl": SOURCE,
        "install": "",
        "missing": "No iOS build, App Store listing, or TestFlight. There is no QR code.",
    },
    {
        "id": "cli",
        "filename": "komboe-cli-linux-x64.zip",
        "patterns": ["komboe-cli-linux-x64.zip", "komboe-cli-linux-x64"],
        "prefix": "cli/",
        "name": "Command line (Linux x64)",
        "platforms": ["Linux"],
        "kind": "cli",
        "channel": "unsigned-testing",
        "docsUrl": SOURCE,
        "install": "Unzip and put `komboe` on your PATH. Set the server URL before signing in. The CLI update command only contacts a host when KOMBOE_CLI_RELEASES_URL is set.",
        "missing": "No CLI zip is in the release artifacts.",
    },
    {
        "id": "wear-os",
        "filename": "komboe-wearos.apk",
        "prefix": "wearos/",
        "name": "Wear OS",
        "platforms": ["Wear OS"],
        "kind": "wear",
        "channel": "unavailable",
        "docsUrl": "https://github.com/GoDeskio/Komboe/tree/main/clients/wearos",
        "install": "The Wear OS companion is a scaffold. The phone app stays the vault authority. A watch build is not published.",
        "missing": "No Wear OS APK. The companion is a scaffold and is not published.",
    },
    {
        "id": "apple-watch",
        "filename": None,
        "prefix": "",
        "name": "Apple Watch",
        "platforms": ["watchOS"],
        "kind": "wear",
        "channel": "unavailable",
        "docsUrl": SOURCE,
        "install": "",
        "missing": "No Apple Watch app. A watchOS build is not set up.",
    },
]

REFUSED = {"komboe-android-debug.apk"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def version_from(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    value = data.get("version") or data.get("versionName")
    return value if isinstance(value, str) and value else None


def find_source(artifacts: Path, item: dict) -> Path | None:
    names = []
    if item.get("filename"):
        names.append(item["filename"])
    for pattern in item.get("patterns") or []:
        names.append(pattern)
    seen: set[Path] = set()
    matches: list[Path] = []
    search_roots = [artifacts]
    prefix = item.get("prefix") or ""
    if prefix:
        search_roots.append(artifacts / prefix.rstrip("/"))
        search_roots.append(artifacts / "android" if item["id"] == "android" else artifacts)
    for root in search_roots:
        if not root.is_dir():
            continue
        for name in names:
            for path in sorted(root.glob(name)):
                if path.is_file() and path.name not in REFUSED and path not in seen:
                    seen.add(path)
                    matches.append(path)
    if not matches:
        return None
    # Prefer a versioned io.komboe.android-*.apk over the generic name.
    versioned = [p for p in matches if p.name.startswith("io.komboe.android-")]
    return versioned[-1] if versioned else matches[-1]


def released_at_for(path: Path, override: str | None) -> str:
    if override:
        return override
    stamp = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def join_url(prefix: str, rel: str) -> str:
    if not prefix:
        return rel
    if prefix.endswith("/"):
        return prefix + rel
    return prefix + "/" + rel


def write_android_feed(asset: dict, dest: Path, extra: dict | None) -> None:
    extra = extra or {}
    payload = {
        "versionName": asset.get("version") or extra.get("versionName"),
        "versionCode": extra.get("versionCode"),
        "apkUrl": asset["url"],
        "sha256": asset["sha256"],
        "minSdk": extra.get("minSdk", 29),
        "releaseNotes": extra.get("releaseNotes") or asset.get("install") or "",
        "releasedAt": asset.get("releasedAt"),
        "size": asset.get("size"),
    }
    if payload["versionCode"] is None:
        # Best-effort numeric yyyymmddnn from versionName like 2026.11.15.2
        name = str(payload["versionName"] or "")
        digits = "".join(ch if ch.isdigit() else "" for ch in name)
        payload["versionCode"] = int(digits) if digits else None
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_windows_feed(artifacts: Path, publish_dir: Path, exe_name: str, version: str | None) -> None:
    """electron-updater reads desktop/latest.yml next to the installer on komboe.com/downloads/desktop."""
    yml = next(artifacts.rglob("latest.yml"), None)
    exe = None
    for path in artifacts.rglob("*.exe"):
        if path.is_file() and (exe is None or path.name == exe_name):
            exe = path
            if path.name == exe_name:
                break
    if yml is not None:
        text = yml.read_text(encoding="utf-8")
        text = re.sub(
            r"(?m)^([ \t]*(?:- )?(?:path|url):[ \t]*).+\.exe[ \t]*$",
            rf"\1{exe_name}",
            text,
        )
    elif exe is not None:
        digest = hashlib.sha512()
        with exe.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        fingerprint = base64.b64encode(digest.digest()).decode("ascii")
        text = (
            f"version: {version or '0.0.0'}\n"
            "files:\n"
            f"  - url: {exe_name}\n"
            f"    sha512: {fingerprint}\n"
            f"    size: {exe.stat().st_size}\n"
            f"path: {exe_name}\n"
            f"sha512: {fingerprint}\n"
        )
    else:
        return
    if not text.endswith("\n"):
        text += "\n"
    dest = publish_dir / "desktop" / "latest.yml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")


def build(
    artifacts: Path,
    version_file: Path | None,
    url_prefix: str,
    publish_dir: Path | None,
    record_checksums: bool = False,
    revision: str | None = None,
    android_meta: dict | None = None,
    released_at: str | None = None,
) -> dict:
    refused = []
    for root in [artifacts, artifacts / "android"]:
        if root.is_dir():
            for name in REFUSED:
                if (root / name).is_file() and name not in refused:
                    refused.append(name)
    refused.sort()
    assets = []
    android_asset = None
    for item in CATALOG:
        source = find_source(artifacts, item)
        published = source is not None
        publish_name = None
        if published:
            if item["id"] == "android" and source.name.startswith("io.komboe.android-"):
                publish_name = source.name
            else:
                publish_name = item["filename"] or source.name
        version = None
        if published:
            if item["id"] == "android" and android_meta and android_meta.get("versionName"):
                version = android_meta["versionName"]
            elif item["kind"] == "extension":
                version = version_from(version_file)
            elif android_meta and item["id"] == "android":
                version = android_meta.get("versionName")
            else:
                version = version_from(version_file)
            if version is None and item["id"] == "android" and source.name.startswith("io.komboe.android-"):
                version = source.name[len("io.komboe.android-"):-len(".apk")] or None
        asset = {
            "id": item["id"],
            "name": item["name"],
            "platforms": item["platforms"],
            "kind": item["kind"],
            "filename": publish_name if published else item["filename"],
            "version": version if published else None,
            "status": "published" if published else "unavailable",
            "channel": item["channel"],
            "sha256": sha256(source) if published else None,
            "size": source.stat().st_size if published else None,
            "releasedAt": released_at_for(source, released_at) if published else None,
            "url": None,
            "docsUrl": item["docsUrl"],
            "install": item["install"],
            "reason": None if published else item["missing"],
            "qr": False,
        }
        if published and item["channel"] == "unavailable":
            asset["channel"] = "unsigned-testing"
        rel = f"{item.get('prefix') or ''}{publish_name}" if published else None
        if published and publish_dir is not None:
            dest = publish_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            asset["url"] = join_url(url_prefix, rel)
            asset["qr"] = True
            asset["status"] = "published"
            asset["reason"] = None
        elif published and record_checksums:
            asset["status"] = "checksum"
            asset["url"] = None
            asset["qr"] = False
            asset["reason"] = "Checksum recorded from a built file. No download URL has been published."
        elif published:
            asset["reason"] = "File is present but no publish directory was set, so it is not downloadable."
            asset["status"] = "unavailable"
            asset["sha256"] = None
            asset["size"] = None
            asset["version"] = None
            asset["releasedAt"] = None
            asset["filename"] = item["filename"]
        assets.append(asset)
        if item["id"] == "android":
            android_asset = asset
    manifest = {
        "schema": 1,
        "revision": revision,
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": "scripts/build-downloads-manifest.py",
        "note": (
            "A download URL is present only when the named file was in the artifact directory "
            "and copied to the publish directory. Store listings are not used. "
            "komboe-android-debug.apk is refused. Public files are served from "
            "https://komboe.com/downloads/ ."
        ),
        "refused": refused,
        "assets": assets,
    }
    if (
        publish_dir is not None
        and android_asset is not None
        and android_asset.get("status") == "published"
        and android_asset.get("url")
        and android_asset.get("sha256")
    ):
        write_android_feed(android_asset, publish_dir / "android" / "latest.json", android_meta)
    windows = next((asset for asset in assets if asset["id"] == "desktop-windows"), None)
    if publish_dir is not None and windows is not None and windows.get("status") == "published":
        write_windows_feed(artifacts, publish_dir, windows["filename"], windows.get("version"))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--version-file", type=Path, default=ROOT / "clients/upstream/apps/browser/src/manifest.v3.json")
    parser.add_argument("--out", type=Path, action="append", required=True)
    parser.add_argument("--publish-dir", type=Path)
    parser.add_argument("--url-prefix", default=PUBLIC_PREFIX)
    parser.add_argument("--record-checksums", action="store_true")
    parser.add_argument("--revision", default=None)
    parser.add_argument("--android-meta", type=Path, help="JSON with versionName, versionCode, minSdk, releaseNotes")
    parser.add_argument("--released-at", default=None, help="ISO-8601 timestamp applied to published files")
    args = parser.parse_args()
    if not args.artifacts.is_dir():
        raise SystemExit(f"artifact directory does not exist: {args.artifacts}")
    meta = None
    if args.android_meta:
        meta = json.loads(args.android_meta.read_text(encoding="utf-8"))
    manifest = build(
        args.artifacts,
        args.version_file,
        args.url_prefix,
        args.publish_dir,
        args.record_checksums,
        args.revision,
        meta,
        args.released_at,
    )
    text = json.dumps(manifest, indent=2) + "\n"
    for dest in args.out:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        print(f"wrote {dest}")


if __name__ == "__main__":
    main()
