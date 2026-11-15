#!/usr/bin/env python3
"""Serve the marketing site with a strict CSP. --api proxies /api and /identity.

/downloads and /downloads/ serve the downloads page. Files under a mounted
directory (KOMBOE_DOWNLOADS_DIR or --downloads-dir, default /var/komboe-downloads
when present) overlay /downloads/* so release APKs and latest.json can be
updated without rebuilding the image. /downloads.html redirects to /downloads.
"""
import argparse
import mimetypes
import os
import urllib.error
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API = None
DOWNLOADS_DIR = None
HOP = {
    "content-type", "accept", "authorization", "device-type",
    "bitwarden-client-name", "bitwarden-client-version",
}

# APK and installer types the stdlib does not always know.
EXTRA_TYPES = {
    ".apk": "application/vnd.android.package-archive",
    ".apks": "application/vnd.android.package-archive",
    ".aab": "application/octet-stream",
    ".deb": "application/vnd.debian.binary-package",
    ".AppImage": "application/octet-stream",
    ".exe": "application/vnd.microsoft.portable-executable",
    ".dmg": "application/x-apple-diskimage",
    ".zip": "application/zip",
}


def policy():
    path = ROOT / "csp.txt"
    base = path.read_text().strip() if path.is_file() else (
        "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; "
        "img-src 'self'; font-src 'self'; connect-src 'self'; form-action 'self'; "
        "base-uri 'self'; object-src 'none'"
    )
    if "frame-ancestors" not in base:
        base += "; frame-ancestors 'none'"
    return base


def proxied(path):
    return path.startswith("/api/") or path.startswith("/identity/") or path in ("/api", "/identity", "/alive")


def safe_under(root: Path, rel: str) -> Path | None:
    if not root or not rel:
        return None
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Content-Security-Policy", policy())
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    def log_message(self, fmt, *args):
        # Path only. Request bodies are never written here.
        super().log_message("%s", args[0] if args else fmt)

    def guess_type(self, path):
        suffix = Path(path).suffix
        if suffix in EXTRA_TYPES:
            return EXTRA_TYPES[suffix]
        if suffix == ".json":
            return "application/json; charset=utf-8"
        return super().guess_type(path)

    def _redirect(self, location, status=301):
        body = f'<a href="{location}">{location}</a>\n'.encode()
        self.send_response(status)
        self.send_header("Location", location)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path):
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Content-Length", str(len(data)))
        if path.suffix.lower() in {".apk", ".zip", ".deb", ".exe", ".dmg", ".appimage"}:
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
            self.send_header("Cache-Control", "public, max-age=300")
        elif path.suffix.lower() == ".json":
            self.send_header("Cache-Control", "public, max-age=60")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)
        query = f"?{parsed.query}" if parsed.query else ""
        if API and proxied(path):
            self._proxy("GET")
            return
        if path == "/downloads.html":
            self._redirect("/downloads" + query)
            return
        if path == "/downloads":
            self._redirect("/downloads/" + query)
            return
        if path == "/downloads/":
            index = ROOT / "downloads" / "index.html"
            if index.is_file():
                self._send_file(index)
                return
        if path.startswith("/downloads/"):
            rel = path[len("/downloads/"):]
            if rel and DOWNLOADS_DIR is not None:
                overlay = safe_under(DOWNLOADS_DIR, rel)
                if overlay is not None and overlay.is_file():
                    self._send_file(overlay)
                    return
        super().do_GET()

    def do_POST(self):
        if API and proxied(urllib.parse.urlparse(self.path).path):
            self._proxy("POST")
            return
        self._drop(405)

    def do_PUT(self):
        if API and proxied(urllib.parse.urlparse(self.path).path):
            self._proxy("PUT")
            return
        self._drop(405)

    def _drop(self, status):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        self.send_error(status)

    def _proxy(self, method):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() in HOP}
        request = urllib.request.Request(API + self.path, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request) as response:
                payload = response.read()
                status = response.status
                ctype = response.headers.get("Content-Type")
        except urllib.error.HTTPError as error:
            payload = error.read()
            status = error.code
            ctype = error.headers.get("Content-Type")
        self.send_response(status)
        if ctype:
            self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def resolve_downloads_dir(explicit: str) -> Path | None:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.environ.get("KOMBOE_DOWNLOADS_DIR")
    if env:
        candidates.append(Path(env))
    candidates.append(Path("/var/komboe-downloads"))
    for path in candidates:
        if path.is_dir():
            return path
    return None


def main():
    global API, DOWNLOADS_DIR
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--api", default="")
    parser.add_argument("--downloads-dir", default="")
    args = parser.parse_args()
    API = args.api.rstrip("/") or None
    DOWNLOADS_DIR = resolve_downloads_dir(args.downloads_dir)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"serving {ROOT} on {args.host}:{args.port} downloads={DOWNLOADS_DIR or '(site tree only)'}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
