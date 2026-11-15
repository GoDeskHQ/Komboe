#!/usr/bin/env python3
"""Fail when Bitwarden branding shows up in Komboe source or in a built package.

Built inputs: an APK, a zip (extension), a web dist directory, an unpacked
desktop app (asar + resources), or an installer directory. The check looks at
bytes that ship, not at the rebrand script's intentions.

Allowed on purpose:
- copyright, license, and source-offer text
- the import-format labels Bitwarden (json), Bitwarden (.json), and Bitwarden (csv)
- protocol headers such as Bitwarden-Client-Name
- PascalCase identifiers such as BitwardenApplication (not shown to people)
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import struct
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DENY = ROOT / "scripts" / "branding_denylist.json"

NAME = re.compile(r"(?<![A-Za-z0-9_@])(?:Bitwarden|Vaultwarden)")
IMPORT_FORMATS = ("Bitwarden (.json)", "Bitwarden (json)", "Bitwarden (csv)")
ALLOW = re.compile(
    r"copyright|GNU GENERAL PUBLIC|licensed under|license agreement|trademark|GPL|AGPL|not affiliated|not endorsed|"
    r"corresponding source|source offer|\bbased on\b|Portions|Third-party|THIRD-PARTY|"
    r"Bitwarden-Client-|Bitwarden \(json\)|Bitwarden \(\.json\)|Bitwarden \(csv\)",
    re.I,
)
COMMENT = re.compile(r"<!--.*?-->|/\*.*?\*/", re.S)
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".icns", ".svg", ".xml"}
TEXT_EXT = {".html", ".htm", ".hbs", ".json", ".js", ".mjs", ".css", ".svg", ".xml", ".txt", ".md", ".yml"}


def load_deny():
    data = json.loads(DENY.read_text(encoding="utf-8"))
    return set(data["sha256"]), tuple(data["shield_paths"])


def sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def allowed(window: str) -> bool:
    if any(label in window for label in IMPORT_FORMATS):
        # Only the label itself is allowed, not a sentence that merely sits near one.
        stripped = window.strip().strip("\"'")
        if stripped in IMPORT_FORMATS or any(stripped.endswith(label) or stripped.startswith(label) for label in IMPORT_FORMATS):
            if "Bitwarden" not in stripped.replace("Bitwarden (json)", "").replace("Bitwarden (.json)", "").replace("Bitwarden (csv)", ""):
                return True
    return ALLOW.search(window) is not None


def identifier_continuation(text: str, end: int) -> bool:
    """PascalCase leftovers such as BitwardenApplication are compile-time names."""
    rest = text[end:end + 48]
    return bool(re.match(r"[A-Z][A-Za-z0-9_]{2,}", rest))


def visible_hits(text: str, path: str):
    hits = []
    if path.endswith("messages.json"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, dict) and isinstance(value.get("message"), str):
                    hits.extend(_scan_chunk(value["message"], f"{path} message {key}"))
            return hits
    if path.endswith((".html", ".htm", ".hbs", ".css", ".scss")):
        text = COMMENT.sub(" ", text)
    hits.extend(_scan_chunk(text, path))
    return hits


def _scan_chunk(text: str, where: str):
    hits = []
    for match in NAME.finditer(text):
        if identifier_continuation(text, match.end()):
            continue
        prefix = text[max(0, match.start() - 40):match.start()]
        # Importer metadata. The visible format label is allowlisted separately.
        if re.search(r"sourceName[\"']?\s*[:=]\s*[\"']?$", prefix):
            continue
        window = text[max(0, match.start() - 160): match.end() + 160]
        if allowed(window):
            continue
        snippet = " ".join(window.split())[:180]
        hits.append(f"{where}: {snippet}")
    return hits


def shield_hits(blob: bytes, path: str, signatures):
    hits = []
    for sig in signatures:
        if sig.encode("ascii") in blob:
            hits.append(f"{path}: upstream shield path")
    return hits


def scan_blob(blob: bytes, path: str, hashes, signatures):
    hits = []
    digest = sha256(blob)
    if digest in hashes:
        hits.append(f"{path}: forbidden image sha256 {digest}")
    hits.extend(shield_hits(blob, path, signatures))
    if b"Bitwarden" in blob or b"Vaultwarden" in blob or b"\x00B\x00i\x00t\x00w\x00a\x00r\x00d\x00e\x00n" in blob:
        text = blob.decode("utf-8", errors="ignore")
        if "Bitwarden" not in text and "Vaultwarden" not in text:
            # UTF-16LE product name inside resources.arsc.
            text = blob.decode("utf-16le", errors="ignore")
        hits.extend(visible_hits(text, path))
    return hits


def walk_source():
    hashes, signatures = load_deny()
    roots = [
        ROOT / "clients/upstream/apps",
        ROOT / "clients/upstream/libs",
        ROOT / "server/upstream/src/static",
        ROOT / "apps/web-marketing",
    ]
    skip = {"node_modules", "dist", "build", ".git", "test", "tests", "spec"}
    hits = []
    for root in roots:
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in skip and not d.endswith(".spec")]
            for name in filenames:
                path = Path(dirpath) / name
                ext = path.suffix.lower()
                if ext not in IMAGE_EXT | TEXT_EXT | {".ttf", ".woff", ".woff2", ".gif"}:
                    continue
                if path.stat().st_size > 40_000_000:
                    continue
                blob = path.read_bytes()
                rel = str(path.relative_to(ROOT))
                if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".icns"} or name.startswith("bwi-font"):
                    digest = sha256(blob)
                    if digest in hashes:
                        hits.append(f"{rel}: forbidden image sha256 {digest}")
                if ext in TEXT_EXT or name.endswith((".svg", ".xml", ".html", ".hbs", ".json")):
                    if b"Bitwarden" in blob or b"Vaultwarden" in blob or any(s.encode() in blob for s in signatures):
                        text = blob.decode("utf-8", errors="ignore")
                        hits.extend(shield_hits(blob, rel, signatures))
                        # Docs and legal source files are scanned only for the shield path.
                        if "/locales/" in rel or rel.endswith((".html", ".hbs", ".svg")) or "messages.json" in rel:
                            hits.extend(visible_hits(text, rel))
                        elif rel.startswith("apps/web-marketing/") and ext in {".html", ".js"}:
                            hits.extend(visible_hits(text, rel))
    return hits


def parse_asar(blob: bytes):
    """Yield (name, bytes) from an Electron asar archive."""
    if len(blob) < 16:
        return
    # size pickle (8 bytes) then a string pickle. JSON begins at byte 16.
    header_pickle_len = struct.unpack_from("<I", blob, 4)[0]
    strlen = struct.unpack_from("<i", blob, 12)[0]
    header = json.loads(blob[16:16 + strlen].decode("utf-8"))
    data_start = 8 + header_pickle_len

    def walk(node, prefix):
        if "files" in node:
            for name, child in node["files"].items():
                yield from walk(child, f"{prefix}{name}/" if "files" in child else f"{prefix}{name}")
        elif "offset" in node:
            start = data_start + int(node["offset"])
            size = int(node["size"])
            yield prefix, blob[start:start + size]

    yield from walk(header, "")


def scan_path(path: Path, hashes, signatures):
    hits = []
    if path.is_dir():
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [d for d in dirnames if d != "node_modules"]
            for name in filenames:
                hits.extend(scan_path(Path(dirpath) / name, hashes, signatures))
        return hits
    if not path.is_file():
        return [f"missing {path}"]
    blob = path.read_bytes()
    rel = str(path)
    if path.name.endswith(".asar"):
        try:
            for name, inner in parse_asar(blob):
                hits.extend(scan_blob(inner, f"{rel}:{name}", hashes, signatures))
        except (json.JSONDecodeError, UnicodeDecodeError, KeyError, struct.error) as exc:
            hits.append(f"{rel}: could not read asar ({exc})")
        return hits
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                if info.is_dir() or info.file_size > 80_000_000:
                    continue
                hits.extend(scan_blob(zf.read(info), f"{rel}:{info.filename}", hashes, signatures))
        return hits
    hits.extend(scan_blob(blob, rel, hashes, signatures))
    return hits


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", action="store_true", help="Scan the repo surfaces that ship")
    parser.add_argument("--built", nargs="*", help="Built APK, zip, dist directory, or unpacked desktop app")
    args = parser.parse_args()
    if not args.source and not args.built:
        parser.error("pass --source and/or --built")
    hashes, signatures = load_deny()
    hits = []
    if args.source:
        hits.extend(walk_source())
    for raw in args.built or []:
        hits.extend(scan_path(Path(raw), hashes, signatures))
    if hits:
        print(f"Bitwarden branding check failed ({len(hits)})")
        print("\n".join(hits[:80]))
        if len(hits) > 80:
            print(f"... {len(hits) - 80} more")
        sys.exit(1)
    print("branding check passed")


if __name__ == "__main__":
    main()
