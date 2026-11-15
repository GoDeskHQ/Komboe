#!/usr/bin/env python3
"""Downloads manifest: only real files are published, bytes match sha256, QR stays local."""
import hashlib
import json
import os
import shutil
import subprocess
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/build-downloads-manifest.py"
PUBLISH = ROOT / "scripts/publish-downloads.py"
COMPONENT = ROOT / "clients/upstream/apps/web/src/app/tools/downloads/downloads.component.ts"
LAYOUT = ROOT / "clients/upstream/apps/web/src/app/layouts/user-layout.component.html"
ROUTING = ROOT / "clients/upstream/apps/web/src/app/oss-routing.module.ts"
MARKETING = ROOT / "apps/web-marketing/downloads.html"
DOCKERFILE = ROOT / "docker/Dockerfile.clients"
FEED_HOST = "https://komboe.com/downloads/"


def run_manifest(artifacts, publish, outs, url_prefix="downloads/", extra=None):
    cmd = ["python3", str(SCRIPT), "--artifacts", str(artifacts), "--publish-dir", str(publish), "--url-prefix", url_prefix]
    for dest in outs:
        cmd.extend(["--out", str(dest)])
    if extra:
        cmd.extend(extra)
    subprocess.check_call(cmd)
    return json.loads(outs[0].read_text(encoding="utf-8"))


def serve(directory):
    os.chdir(directory)
    from http.server import SimpleHTTPRequestHandler
    server = ThreadingHTTPServer(("127.0.0.1", 0), SimpleHTTPRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def qr_roundtrip(url, dest):
    try:
        import segno
    except ImportError:
        print("QR test skipped (segno not installed)")
        return
    if shutil.which("zbarimg") is None:
        print("QR test skipped (zbarimg not installed)")
        return
    segno.make(url, error="m").save(dest, scale=4)
    decoded = subprocess.check_output(["zbarimg", "--quiet", "--raw", str(dest)], text=True).strip()
    assert decoded == url, (decoded, url)


def test_publish_and_refuse_debug_apk(work):
    artifacts = work / "artifacts"
    publish = work / "www/downloads"
    artifacts.mkdir(parents=True)
    payload = b"PK\x03\x04komboe-extension-fixture-not-a-store-build"
    (artifacts / "komboe-chrome-mv3.zip").write_bytes(payload)
    (artifacts / "komboe-android-debug.apk").write_bytes(b"debug-apk-must-not-ship")
    out = work / "komboe-downloads.json"
    manifest = run_manifest(artifacts, publish, [out])

    assert "komboe-android-debug.apk" in manifest["refused"]
    by_id = {asset["id"]: asset for asset in manifest["assets"]}
    for required in (
        "extension-chromium-mv3", "extension-firefox", "extension-safari",
        "desktop-windows", "desktop-linux-deb", "desktop-linux-appimage",
        "desktop-macos", "android", "ios", "cli", "wear-os", "apple-watch",
    ):
        assert required in by_id, required
    ext = by_id["extension-chromium-mv3"]
    assert ext["status"] == "published"
    assert ext["sha256"] == hashlib.sha256(payload).hexdigest()
    assert ext["size"] == len(payload)
    assert ext["version"] == "2026.10.1"
    assert ext["url"] == "downloads/komboe-chrome-mv3.zip"
    assert ext["releasedAt"]
    assert ext["qr"] is True
    assert "unsigned" in ext["channel"]
    assert (publish / "komboe-chrome-mv3.zip").read_bytes() == payload

    android = by_id["android"]
    ios = by_id["ios"]
    macos = by_id["desktop-macos"]
    windows = by_id["desktop-windows"]
    safari = by_id["extension-safari"]
    cli = by_id["cli"]
    wear = by_id["wear-os"]
    watch = by_id["apple-watch"]
    assert android["status"] == "unavailable" and android["url"] is None and android["qr"] is False
    assert ios["status"] == "unavailable" and ios["qr"] is False and "QR" in ios["reason"]
    assert macos["status"] == "unavailable" and "signing" in macos["reason"].lower()
    assert windows["status"] == "unavailable"
    assert safari["status"] == "unavailable" and "Safari" in safari["reason"]
    assert cli["status"] == "unavailable"
    assert wear["status"] == "unavailable" and watch["status"] == "unavailable"
    blob = json.dumps(manifest)
    for banned in ("play.google.com", "apps.apple.com", "chromewebstore", "nngceckbapebfimnlniiiahkandclblb", "downloads.komboe.com"):
        assert banned not in blob, banned
    return manifest


def test_android_feed(work):
    artifacts = work / "apk-artifacts"
    publish = work / "apk-publish"
    artifacts.mkdir(parents=True)
    apk = b"apk-fixture-bytes-not-a-real-package" * 50
    (artifacts / "io.komboe.android-2026.11.15.2.apk").write_bytes(apk)
    meta = {"versionName": "2026.11.15.2", "versionCode": 2026111502, "minSdk": 29, "releaseNotes": "Feed on komboe.com/downloads"}
    meta_path = artifacts / "meta.json"
    meta_path.write_text(json.dumps(meta))
    out = work / "with-android.json"
    manifest = run_manifest(
        artifacts, publish, [out], url_prefix=FEED_HOST,
        extra=["--android-meta", str(meta_path), "--released-at", "2026-11-15T00:00:00Z"],
    )
    android = next(a for a in manifest["assets"] if a["id"] == "android")
    assert android["status"] == "published"
    assert android["version"] == "2026.11.15.2"
    assert android["sha256"] == hashlib.sha256(apk).hexdigest()
    assert android["size"] == len(apk)
    assert android["releasedAt"] == "2026-11-15T00:00:00Z"
    assert android["url"] == FEED_HOST + "android/io.komboe.android-2026.11.15.2.apk"
    assert (publish / "android" / "io.komboe.android-2026.11.15.2.apk").read_bytes() == apk
    feed = json.loads((publish / "android" / "latest.json").read_text())
    assert feed["versionName"] == "2026.11.15.2"
    assert feed["versionCode"] == 2026111502
    assert feed["apkUrl"] == android["url"]
    assert feed["sha256"] == android["sha256"]
    assert "downloads.komboe.com" not in json.dumps(feed)


def test_windows_feed(work):
    artifacts = work / "win-artifacts"
    publish = work / "win-publish"
    artifacts.mkdir(parents=True)
    exe = b"MZ-komboe-setup-fixture"
    (artifacts / "komboe-desktop-win-x64-setup.exe").write_bytes(exe)
    (artifacts / "latest.yml").write_text(
        "version: 2026.11.15\nfiles:\n  - url: Komboe Setup 2026.10.2.exe\n    sha512: aaa\n    size: 1\npath: Komboe Setup 2026.10.2.exe\nsha512: aaa\n"
    )
    out = work / "with-windows.json"
    manifest = run_manifest(artifacts, publish, [out], url_prefix=FEED_HOST)
    windows = next(a for a in manifest["assets"] if a["id"] == "desktop-windows")
    assert windows["status"] == "published"
    assert windows["filename"] == "komboe-desktop-win-x64-setup.exe"
    assert (publish / "desktop" / "komboe-desktop-win-x64-setup.exe").read_bytes() == exe
    feed = (publish / "desktop" / "latest.yml").read_text(encoding="utf-8")
    assert "url: komboe-desktop-win-x64-setup.exe" in feed
    assert "path: komboe-desktop-win-x64-setup.exe" in feed
    assert "Komboe Setup" not in feed


def test_http_and_qr(work, ext_url_rel, payload, sha):
    server = serve(work / "www")
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}/"
        downloaded = urllib.request.urlopen(base + ext_url_rel, timeout=10).read()
        assert downloaded == payload
        assert hashlib.sha256(downloaded).hexdigest() == sha
        qr_roundtrip(base + ext_url_rel, work / "qr.png")
    finally:
        server.shutdown()


def test_marketing_and_repo():
    layout = LAYOUT.read_text(encoding="utf-8")
    routing = ROUTING.read_text(encoding="utf-8")
    component = COMPONENT.read_text(encoding="utf-8")
    assert layout.count('data-testid="nav-downloads"') == 2
    assert 'path: "downloads"' in routing
    assert 'path: "register"' in routing
    assert "app-vault-onboarding" not in (ROOT / "clients/upstream/apps/web/src/app/vault/individual-vault/vault.component.html").read_text(encoding="utf-8")
    assert "qrious.min.js" in component
    assert "qrserver" not in component and "chart.googleapis" not in component
    assert "komboe-android-debug" not in component
    marketing = MARKETING.read_text(encoding="utf-8")
    directory = (ROOT / "apps/web-marketing/downloads/index.html").read_text(encoding="utf-8")
    committed = json.loads((ROOT / "distribution/komboe-downloads.json").read_text(encoding="utf-8"))
    published_copy = json.loads((ROOT / "apps/web-marketing/komboe-downloads.json").read_text(encoding="utf-8"))
    assert published_copy == committed
    assert "coming soon" not in marketing.lower()
    assert "BROWSER-EXTENSIONS.md" in marketing
    assert "downloads.komboe.com" not in marketing
    assert "https://komboe.com/downloads" in marketing
    for asset in committed["assets"]:
        assert f'marketing-download-{asset["id"]}' in marketing
        assert f'marketing-download-{asset["id"]}' in directory
        if asset["status"] != "published":
            assert asset["reason"] in marketing
            assert asset["qr"] is False
        else:
            assert asset["sha256"] in marketing
            assert str(asset["version"]) in marketing
            assert "SHA-256" in marketing
    docker = DOCKERFILE.read_text(encoding="utf-8")
    assert "build-downloads-manifest.py" in docker
    assert "komboe-chrome-mv3" in docker
    strings = (ROOT / "mobile/self-update/komboe_update_strings.xml").read_text(encoding="utf-8")
    assert "https://komboe.com/downloads/android/latest.json" in strings
    assert "downloads.komboe.com" not in strings
    assert PUBLISH.is_file()


def test_serve_overlay(work):
    import importlib.util
    import sys
    site = ROOT / "apps/web-marketing"
    overlay = work / "overlay"
    (overlay / "android").mkdir(parents=True)
    feed = {"versionName": "overlay", "versionCode": 1, "apkUrl": "https://komboe.com/downloads/android/x.apk", "sha256": "a" * 64}
    (overlay / "android" / "latest.json").write_text(json.dumps(feed))
    spec = importlib.util.spec_from_file_location("komboe_serve", site / "serve.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["komboe_serve"] = mod
    spec.loader.exec_module(mod)
    mod.DOWNLOADS_DIR = overlay
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), mod.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        port = httpd.server_address[1]
        class NoRedir(urllib.request.HTTPErrorProcessor):
            def http_response(self, request, response):
                return response
        def raw(path):
            req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
            return urllib.request.build_opener(NoRedir).open(req, timeout=10)
        r = raw("/downloads.html")
        assert r.status in (301, 302) and r.headers.get("Location", "").startswith("/downloads")
        r = raw("/downloads")
        assert r.status in (301, 302) and r.headers.get("Location", "").startswith("/downloads/")
        page = urllib.request.urlopen(f"http://127.0.0.1:{port}/downloads/", timeout=10).read().decode()
        assert "Download Komboe" in page
        body = urllib.request.urlopen(f"http://127.0.0.1:{port}/downloads/android/latest.json", timeout=10).read()
        assert json.loads(body)["versionName"] == "overlay"
    finally:
        httpd.shutdown()


def main():
    work = Path("/tmp/komboe-downloads-test")
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()
    manifest = test_publish_and_refuse_debug_apk(work)
    ext = next(a for a in manifest["assets"] if a["id"] == "extension-chromium-mv3")
    payload = (work / "www/downloads/komboe-chrome-mv3.zip").read_bytes()
    test_http_and_qr(work, ext["url"], payload, ext["sha256"])
    test_android_feed(work)
    test_windows_feed(work)
    empty = work / "empty"
    empty.mkdir()
    empty_out = work / "empty.json"
    empty_manifest = run_manifest(empty, work / "empty-publish", [empty_out])
    assert all(asset["status"] == "unavailable" and asset["url"] is None and asset["qr"] is False for asset in empty_manifest["assets"])
    test_marketing_and_repo()
    test_serve_overlay(work)
    print("DOWNLOADS MANIFEST PASS", ext["sha256"])


if __name__ == "__main__":
    main()
