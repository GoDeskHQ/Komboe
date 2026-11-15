#!/usr/bin/env python3
"""Fail when Bitwarden branding shows up in Komboe source or in a built package.

Built inputs: an APK, a zip (extension), a web dist directory, an unpacked
desktop app (asar + resources), or an installer directory. The check looks at
bytes that ship, not at the rebrand script's intentions.

Allowed on purpose:
- license and source-offer text (the notices screen, not the About copyright line)
- the import-format labels Bitwarden (json), Bitwarden (.json), and Bitwarden (csv)
- protocol header names such as Bitwarden-Client-Name
- PascalCase identifiers and package paths (not shown to people)

The name check is case-insensitive and includes misspellings (Bitward, Bitwarde,
BItwarden), Latin tokens within edit distance 2 of "bitwarden", and the
transliterations in scripts/brand_names.py. Upstream image and SVG bytes,
including toolbar icons and the download QR, are rejected by sha256.
`bitwarden_export` is rejected wherever it is spelled out.
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

from brand_names import fuzzy_spans, needle_blobs, transliteration_spans

ROOT = Path(__file__).resolve().parents[1]
DENY = ROOT / "scripts" / "branding_denylist.json"

NAME_START = re.compile(r"(?i)(?:(?<![A-Za-z0-9_@])|(?<=\\n))(?:bit\s*ward|vaultwarden)")
IMPORT_FORMATS = ("Bitwarden (.json)", "Bitwarden (json)", "Bitwarden (csv)")
ALLOW = re.compile(
    r"GNU GENERAL PUBLIC|licensed under|license agreement|not affiliated|not endorsed|"
    r"corresponding source|source offer|\bbased on\b|Portions|Third-party|THIRD-PARTY|trademark|GPL|AGPL",
    re.I,
)
CODE_SUFFIX = re.compile(r"(?:json|csv|fill|password|browser|web|desktop|license)", re.I)
SKIP_TEXT_EXT = {".wasm", ".node", ".so", ".dll", ".dylib", ".pak", ".bin", ".dat", ".exe", ".pdb"}
COMMENT = re.compile(r"<!--.*?-->|/\*.*?\*/", re.S)
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".icns", ".svg", ".xml"}
TEXT_EXT = {".html", ".htm", ".hbs", ".json", ".js", ".mjs", ".css", ".svg", ".xml", ".txt", ".md", ".yml"}


def load_deny():
    data = json.loads(DENY.read_text(encoding="utf-8"))
    return set(data["sha256"]), tuple(data["shield_paths"])


def sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _overlaps(start: int, end: int, spans) -> bool:
    return any(not (end <= left or start >= right) for left, right in spans)


def product_spans(text: str):
    """Yield (start, end) of a product-name variant without swallowing camelCase suffixes."""
    found = []
    for match in NAME_START.finditer(text):
        end = match.end()
        if match.group(0).lower().startswith("vaultwarden"):
            found.append((match.start(), end))
            continue
        # Include the "en" of Bitwarden, not a following identifier (bitwardenjson).
        if text[end:end + 2].lower() == "en":
            end += 2
        elif text[end:end + 1].lower() == "e" and not text[end + 1:end + 2].isalpha():
            end += 1
        chunk = re.sub(r"\s+", "", text[match.start():end])
        if chunk.isupper():
            while end < len(text) and text[end].isupper():
                end += 1
        found.append((match.start(), end))
    for start, end in transliteration_spans(text):
        if not _overlaps(start, end, found):
            found.append((start, end))
    for start, end in fuzzy_spans(text):
        if not _overlaps(start, end, found):
            found.append((start, end))
    for start, end in found:
        yield start, end


def still_branded(text: str) -> bool:
    return next(product_spans(text), None) is not None


def allowed(window: str) -> bool:
    if any(label in window for label in IMPORT_FORMATS):
        stripped = window.strip().strip("\"'")
        rest = stripped
        for label in IMPORT_FORMATS:
            rest = rest.replace(label, "")
        if not still_branded(rest):
            return True
    # Importer format name. Minified bundles keep name/displayName/sourceName "Bitwarden".
    if re.search(r'(?:sourceName|displayName|featuredImporter)"?\s*[:=]', window) and re.search(
        r'"Bitwarden"', window
    ):
        return True
    return ALLOW.search(window) is not None


def isolated_identifier(text: str, start: int, end: int) -> bool:
    """Resource keys and class names packed in dex/arsc, not a sentence."""
    window = text[max(0, start - 8): end + 8]
    if "\x00" not in window:
        return False
    return not any(ch.isspace() for ch in window)


def code_context(text: str, start: int, end: int) -> bool:
    """Package paths, file names, translation keys, and protocol tokens are not product branding."""
    prev = text[start - 1] if start else ""
    nxt = text[end:end + 40]
    if prev and prev in "@_-:":
        return True
    # Quoted lowercase ids: i18n keys, importer ids, resource names.
    token = text[start:end]
    if prev == '"' and nxt[:1] == '"' and token == "bitwarden":
        return True
    if isolated_identifier(text, start, end):
        return True
    # bitwarden_export is the vault download name, not an identifier.
    if nxt[:1] in {"_", "-"} and not nxt.lower().startswith("_export"):
        return True
    if re.match(r"\.(?:scss|hbs|css|png|svg|js)\b", nxt):
        return True
    if nxt.startswith("Client"):
        return True
    if prev == "/" and "github.com/" in text[max(0, start - 80):start]:
        return True
    if prev == "/" and (nxt[:1] in "/" or re.match(r"\.(?:ts|js|mjs|svg|png|json|xml|kt|css|html)\b", nxt)):
        return True
    if prev == ".":
        return True
    if nxt.startswith(".") and re.match(r"\.(?:com|eu|net|pw|gov|atlassian)\b", nxt):
        return True
    if nxt.startswith(":{") or nxt.startswith("://") or nxt.startswith(':"') or nxt.startswith(":'"):
        return True
    if CODE_SUFFIX.match(nxt):
        return True
    # CamelCase identifier suffix: BitwardenIcon, bitwardenAccount.
    if nxt[:1].isupper():
        return True
    return False


def identifier_continuation(text: str, end: int) -> bool:
    """PascalCase leftovers such as BitwardenApplication are compile-time names."""
    rest = text[end:end + 48]
    return bool(re.match(r"[A-Z][A-Za-z0-9_]{2,}", rest))


def visible_hits(text: str, path: str):
    hits = []
    if path.endswith("messages.json"):
        try:
            data = json.loads(text.lstrip("\ufeff"))
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            for key, value in data.items():
                if not isinstance(value, dict):
                    continue
                for field in ("message", "description"):
                    raw = value.get(field)
                    if isinstance(raw, str):
                        hits.extend(_scan_chunk(raw, f"{path} {field} {key}"))
            return hits
    if path.endswith((".js", ".mjs", ".ts")):
        text = strip_js_comments(text)
    elif path.endswith((".html", ".htm", ".hbs", ".css", ".scss")):
        text = COMMENT.sub(" ", text)
    hits.extend(_scan_chunk(text, path))
    return hits


def resource_key(text: str, start: int, end: int, where: str) -> bool:
    """String-pool keys inside an APK, not a sentence in the UI."""
    path = where.lower()
    if not (path.endswith(".dex") or path.endswith(".arsc") or path.endswith("androidmanifest.xml")):
        return False
    token = text[start:end]
    if token.lower() not in {"bitwarden", "vaultwarden"}:
        return False
    nxt = text[end] if end < len(text) else ""
    if nxt.isalpha():
        return False
    before = text[max(0, start - 40):start]
    # A real sentence has a word that is not glued to an underscore.
    return re.search(r"(?<![_\w])[^\W\d_]{3,}(?=\s)", before) is None


_HOST = re.compile(r"(?i)(?<![A-Za-z0-9-])(?:https?://)?(?:[a-z0-9-]+\.)*bitwarden\.com\b")
_PROTOCOL_LABELS = {"api", "identity", "vault", "icons", "events", "notifications", "send", "gw", "scim"}


def host_hits(text: str, where: str):
    """bitwarden.com in any host. Isolated protocol URLs stay; prose and www do not."""
    hits = []
    for match in _HOST.finditer(text):
        host = re.sub(r"(?i)^https?://", "", match.group(0))
        labels = [part.lower() for part in host.split(".") if part.lower() not in {"bitwarden", "com"}]
        before = text[max(0, match.start() - 60):match.start()]
        after = text[match.end():match.end() + 40]
        prose = bool(re.search(r"[^\W\d_]{2,}\s+$", before)) or bool(re.search(r"^\s+[^\W\d_]{2,}", after))
        protocol = len(labels) == 1 and labels[0] in _PROTOCOL_LABELS and not prose
        bare = len(labels) == 0 and not prose
        if protocol or bare:
            continue
        window = text[max(0, match.start() - 80):match.end() + 80]
        if allowed(window):
            continue
        snippet = " ".join(window.split())[:180]
        hits.append(f"{where}: {snippet}")
    return hits


def _scan_chunk(text: str, where: str):
    hits = []
    for start, end in product_spans(text):
        if identifier_continuation(text, end) or code_context(text, start, end):
            continue
        if resource_key(text, start, end, where):
            continue
        prefix = text[max(0, start - 48):start]
        if "com.bitwarden" in prefix or "com/bitwarden" in prefix or "userAgentItem" in prefix:
            continue
        window = text[max(0, start - 160): end + 160]
        if allowed(window):
            continue
        snippet = " ".join(window.split())[:180]
        hits.append(f"{where}: {snippet}")
    hits.extend(host_hits(text, where))
    if re.search(r"(?i)bitwarden_export", text):
        hits.append(f"{where}: bitwarden_export")
    if re.search(
        r"""(?i)["']bitwarden["']\s*\+(?:\s*\([^)]{0,200}\)\s*\+)?\s*["']_export_""",
        text,
    ):
        hits.append(f"{where}: bitwarden export filename prefix")
    if re.search(r">\s*aultwarden", text, re.I):
        hits.append(f"{where}: split Vaultwarden wordmark")
    return hits


def shield_hits(blob: bytes, path: str, signatures):
    hits = []
    for sig in signatures:
        if sig.encode("ascii") in blob:
            hits.append(f"{path}: upstream shield path")
    return hits


def skip_text(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    if normalized.endswith(".map") or normalized.endswith(".js.map"):
        return True
    if any(normalized.endswith(ext) for ext in SKIP_TEXT_EXT):
        return True
    # Generated SDK comments and API docs are not product UI.
    if "/node_modules/@bitwarden/sdk-internal/" in normalized or "bitwarden_wasm_internal" in normalized:
        return True
    return False


def carries_name(blob: bytes) -> bool:
    lower = blob.lower()
    if b"bitward" in lower or b"vaultwarden" in lower:
        return True
    if b"b\x00i\x00t\x00w" in blob or b"B\x00i\x00t\x00w" in blob or b"B\x00I\x00t\x00W" in blob:
        return True
    return any(needle in blob for needle in needle_blobs())


def strip_js_comments(text: str) -> str:
    """Drop // and /* */ comments without eating https:// or quoted text."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in ('"', "'", "`"):
            quote = c
            out.append(c)
            i += 1
            while i < n:
                out.append(text[i])
                if text[i] == "\\":
                    i += 1
                    if i < n:
                        out.append(text[i])
                elif text[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            i += 2
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i = min(n, i + 2)
            continue
        out.append(c)
        i += 1
    return "".join(out)


def scan_blob(blob: bytes, path: str, hashes, signatures):
    hits = []
    digest = sha256(blob)
    if digest in hashes:
        hits.append(f"{path}: forbidden image sha256 {digest}")
    hits.extend(shield_hits(blob, path, signatures))
    if skip_text(path):
        return hits
    if carries_name(blob):
        text = blob.decode("utf-8", errors="ignore")
        if not still_branded(text):
            # UTF-16LE product name inside resources.arsc and other resource tables.
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
                if ext == ".ts" and not (name.endswith(".icon.ts") or name == "shield.ts"):
                    blob = path.read_bytes()
                    rel = str(path.relative_to(ROOT))
                    if any(sig.encode() in blob for sig in signatures):
                        hits.extend(shield_hits(blob, rel, signatures))
                    continue
                icon_ts = name.endswith(".icon.ts") or name in {
                    "admin-console.ts", "secrets-manager.ts", "secrets-manager-alt.ts",
                    "provider-portal.ts", "business-unit-portal.ts", "shield.ts", "bitwarden-icon.ts",
                }
                if ext not in IMAGE_EXT | TEXT_EXT | {".ttf", ".woff", ".woff2", ".gif"} and not icon_ts:
                    continue
                if path.stat().st_size > 40_000_000:
                    continue
                blob = path.read_bytes()
                rel = str(path.relative_to(ROOT))
                if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".icns", ".svg"} or name.startswith("bwi-font") or icon_ts:
                    digest = sha256(blob)
                    if digest in hashes:
                        hits.append(f"{rel}: forbidden image sha256 {digest}")
                if ext in TEXT_EXT or icon_ts or name.endswith((".svg", ".xml", ".html", ".hbs", ".json")):
                    if carries_name(blob) or any(s.encode() in blob for s in signatures):
                        text = blob.decode("utf-8", errors="ignore")
                        hits.extend(shield_hits(blob, rel, signatures))
                        if rel.endswith(".md"):
                            continue
                        if (
                            "/locales/" in rel
                            or rel.endswith((".html", ".hbs", ".svg", ".icon.ts"))
                            or "messages.json" in rel
                            or icon_ts
                            or "/libs/assets/" in rel
                            or (rel.startswith("apps/web-marketing/") and ext in {".html", ".js"})
                        ):
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
