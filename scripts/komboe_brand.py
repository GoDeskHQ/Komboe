#!/usr/bin/env python3
"""Paint official Komboe kit artwork over upstream Bitwarden images.

Images come from brand/komboe-kit. This module does not draw a new mark.
PIL is required: a missing Pillow install aborts instead of leaving the
upstream art in place.
"""
from __future__ import annotations

import glob
import hashlib
import io
import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIT = os.path.join(ROOT, "brand", "komboe-kit")
CLIENTS = os.path.join(ROOT, "clients", "upstream")

NAVY = (11, 27, 51, 255)
OFFWHITE = (240, 236, 231, 255)
INK = (7, 7, 2, 255)

# Upstream shield outlines. A rebuilt package that still contains either path fails the branding check.
SHIELD_PATHS = (
    "M19.7612 2.25001C19.6886 2.17064",
    "M843.1445333333332 799.9995733333333",
)

IMPORT_FORMATS = ("Bitwarden (.json)", "Bitwarden (json)", "Bitwarden (csv)")


def require_pil():
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        sys.exit("PIL is required for the Komboe rebrand; refusing to skip image replacement")
    return Image, ImageDraw


def _png(src, size, bg=None):
    Image, _ = require_pil()
    im = Image.open(src).convert("RGBA")
    im.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", size, bg if bg is not None else (0, 0, 0, 0))
    canvas.paste(im, ((size[0] - im.width) // 2, (size[1] - im.height) // 2), im)
    return canvas


def _save_png(im, dest):
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    _write_bytes(dest, buf.getvalue())


def _write_bytes(dest, data: bytes):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest) and open(dest, "rb").read() == data:
        return False
    open(dest, "wb").write(data)
    return True


def _write_text(dest, text: str):
    if os.path.exists(dest) and open(dest, encoding="utf-8").read() == text:
        return False
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    open(dest, "w", encoding="utf-8").write(text)
    return True


def mark_png(size, variant="navy-gradient"):
    """Official mark, letterboxed to size. variant: navy-gradient, mono-black, mono-white, navy."""
    src = os.path.join(KIT, "01-master", f"komboe-mark-{variant}.png")
    if not os.path.exists(src):
        src = os.path.join(KIT, "09-desktop", "electron", "icon-1024.png")
    return _png(src, size)


def wordmark_png(size, variant="navy"):
    src = os.path.join(KIT, "05-wordmark-lockups", f"komboe-lockup-horizontal-{variant}.png")
    return _png(src, size)


def plate(size, dark=False):
    """Official mark and horizontal lockup on a navy or off-white field. Same mark, no new drawing."""
    Image, _ = require_pil()
    bg = NAVY if dark else OFFWHITE
    canvas = Image.new("RGBA", size, bg)
    mark_name = "mono-white" if dark else "navy"
    word_name = "mono-white" if dark else "navy"
    side = max(16, min(size) // 3)
    mark = mark_png((side, side), mark_name)
    canvas.paste(mark, ((size[0] - side) // 2, max(0, size[1] // 2 - side)), mark)
    word_w = max(16, int(size[0] * 0.72))
    word_h = max(12, min(size[1] // 6, int(word_w * 470 / 1681)))
    word = wordmark_png((word_w, word_h), word_name)
    y = min(size[1] - word_h - 4, size[1] // 2 + side // 3)
    canvas.paste(word, ((size[0] - word_w) // 2, max(0, y)), word)
    return canvas


def replace_raster(dest, im):
    ext = os.path.splitext(dest)[1].lower()
    buf = io.BytesIO()
    if ext == ".bmp":
        im.convert("RGB").save(buf, "BMP")
    elif ext in (".jpg", ".jpeg"):
        im.convert("RGB").save(buf, "JPEG", quality=90)
    else:
        im.save(buf, "PNG", optimize=True)
    return _write_bytes(dest, buf.getvalue())


def fit_file(src_png, dest):
    Image, _ = require_pil()
    if os.path.exists(dest):
        size = Image.open(dest).size
    else:
        size = Image.open(src_png).size
    return replace_raster(dest, _png(src_png, size))


def copy_ico(src, dest):
    return _write_bytes(dest, open(src, "rb").read())


def sidebar_bmp(dest):
    """NSIS installer sidebar is 164x314. Official mark on the navy field."""
    Image, _ = require_pil()
    size = (164, 314)
    if os.path.exists(dest):
        size = Image.open(dest).size
    canvas = Image.new("RGB", size, NAVY[:3])
    side = int(min(size) * 0.62)
    mark = mark_png((side, side), "mono-white").convert("RGBA")
    canvas.paste(mark, ((size[0] - side) // 2, (size[1] - side) // 2), mark)
    return replace_raster(dest, canvas)


def svg_text(src):
    return open(src, encoding="utf-8").read()


def replace_svg(dest, src):
    return _write_text(dest, svg_text(src))


MARK_D = re.search(
    r'd="([^"]+)"',
    open(os.path.join(KIT, "01-master", "komboe-mark-mono-black.svg"), encoding="utf-8").read(),
).group(1)


def _font_mark_path():
    """Official mark path, scaled into the bwi em box (y-up, 1024 units)."""
    from fontTools.misc.transform import Transform
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.svgLib.path import parse_path

    pen = SVGPathPen(None)
    # SVG transform on the master mark, then flip into the font's y-up box.
    svg_tf = Transform(1, 0, 0, 1, 321.99, 245.76).scale(1.10473).translate(-340, -271)
    font_tf = Transform(0.72, 0, 0, -0.72, 140, 760)
    parse_path(MARK_D, TransformPen(pen, font_tf.transform(svg_tf)))
    return pen.getCommands()


def replace_bwi_shield(font_dir):
    """Point the bwi shield glyph (U+F169, used by bwi-shield and bwi-bitwarden-shield) at the mark."""
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.svgLib.path import parse_path
    from fontTools.ttLib import TTFont

    commands = _font_mark_path()
    svg = os.path.join(font_dir, "bwi-font.svg")
    if os.path.exists(svg):
        text = open(svg, encoding="utf-8").read()
        text2, n = re.subn(
            r'(glyph-name="bitwarden-shield"[^>]*d=")[^"]+(")',
            lambda m: m.group(1) + commands + m.group(2),
            text,
            count=1,
        )
        if n != 1:
            sys.exit("bwi-font.svg is missing the bitwarden-shield glyph")
        _write_text(svg, text2)

    ttf_path = os.path.join(font_dir, "bwi-font.ttf")
    if not os.path.exists(ttf_path):
        return
    font = TTFont(ttf_path)
    glyph_set = font.getGlyphSet()
    name = "bitwarden-shield"
    if name not in glyph_set:
        # Some builds keep the production name; the unicode cmap still points at U+F169.
        cmap = font.getBestCmap() or {}
        name = cmap.get(0xF169)
    if not name:
        sys.exit("bwi font has no U+F169 shield glyph")
    from fontTools.misc.transform import Transform
    from fontTools.pens.cu2quPen import Cu2QuPen

    pen = TTGlyphPen(glyph_set)
    # glyf in this font stores quadratic outlines. The official mark is cubic.
    qu = Cu2QuPen(pen, max_err=1.0, reverse_direction=False)
    svg_tf = Transform(1, 0, 0, 1, 321.99, 245.76).scale(1.10473).translate(-340, -271)
    font_tf = Transform(0.72, 0, 0, -0.72, 140, 760)
    parse_path(MARK_D, TransformPen(qu, font_tf.transform(svg_tf)))
    font["glyf"][name] = pen.glyph()
    font.save(ttf_path)
    for ext, flavor in (("woff", "woff"), ("woff2", "woff2")):
        out = os.path.join(font_dir, f"bwi-font.{ext}")
        subset = TTFont(ttf_path)
        subset.flavor = flavor
        subset.save(out)
        subset.close()
    font.close()


def shield_svg(dest):
    """libs/assets material icon. Same official mark, 24px viewBox."""
    body = (
        '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">'
        '<g transform="translate(2.2,1.6) scale(0.0191)">'
        f'<path fill="currentColor" fill-rule="evenodd" transform="translate(321.99,245.76) scale(1.10473) translate(-340,-271)" d="{MARK_D}"/>'
        "</g></svg>\n"
    )
    return _write_text(dest, body)


# Case and spelling variants the exact "Bitwarden" replace left in locales:
# BItwarden, BitWarden, Bitward, Bitwarde, bitwarden.firma.dk, and inflections.
# The match stops before camelCase suffixes (BitwardenString) and code ids (bitwardenjson).
# Also a boundary after an Android "\n" escape, which otherwise looks like a letter.
BRAND_NAME = re.compile(r"(?i)(?:(?<![A-Za-z0-9_@./])|(?<=\\n))bit\s*ward(?:en)?")
CODE_SUFFIXES = {
    "json", "csv", "fill", "passwordprotected", "browser", "web", "desktop",
    "license", "premium", "organization", "account", "extension",
}
LICENSE_LINE = re.compile(
    r"GNU GENERAL PUBLIC|licensed under|not affiliated|not endorsed|corresponding source|source offer",
    re.I,
)


def rewrite_visible(text: str) -> str:
    """Replace product-name variants in user-visible text. Import-format labels stay."""
    parts = []
    rest = text
    while rest:
        idxs = [(rest.find(label), label) for label in IMPORT_FORMATS]
        idxs = [(i, label) for i, label in idxs if i >= 0]
        if not idxs:
            parts.append(_rename(rest))
            break
        i, label = min(idxs)
        parts.append(_rename(rest[:i]))
        parts.append(label)
        rest = rest[i + len(label):]
    return "".join(parts)


def _brand_end(text: str, end: int) -> int | None:
    """End index to replace, or None when this is a code identifier."""
    if end < len(text) and (text[end].isupper() or text[end] == "_"):
        return None
    extra = re.match(r"[a-z]+", text[end:])
    if extra:
        suffix = extra.group(0)
        if suffix in CODE_SUFFIXES or len(suffix) > 6:
            return None
        return end + extra.end()
    return end


def _rename(text: str) -> str:
    text = re.sub(r"(?i)©\s*bit\s*ward(?:en)?(?:\s+inc\.?)?", "© Komboe", text)
    # Example hosts in user-facing copy. Protocol hosts (api., vault., identity.) are not this shape.
    text = re.sub(r"(?i)(https?://)bitwarden\.", r"\1komboe.", text)
    text = re.sub(r"(?i)bitwarden\.\s*com", "komboe.com", text)
    pieces = []
    cursor = 0
    for match in BRAND_NAME.finditer(text):
        end = _brand_end(text, match.end())
        if end is None:
            continue
        pieces.append(text[cursor:match.start()])
        pieces.append("Komboe")
        cursor = end
    pieces.append(text[cursor:])
    text = "".join(pieces)
    text = re.sub(r"(?<![A-Za-z0-9_@./])Vaultwarden(?![A-Za-z0-9_])", "Komboe", text)
    return text


def rewrite_locale(text: str) -> str:
    out = []
    for line in text.splitlines(keepends=True):
        if ('"message":' in line or '"description":' in line) and not LICENSE_LINE.search(line):
            out.append(rewrite_visible(line))
        else:
            out.append(line)
    return "".join(out)


UPSTREAM_SHIELD_FRAGMENTS = (
    "M15.6599 3.17501",
    "M18.7697 12.9217",
    "M22.01 17.055V4.135",
    "M75.971 26.765",
)

# Product wordmarks and the account-switcher shield. Filenames stay so imports keep working.
LOCKUP_ICONS = {
    "libs/assets/src/svg/svgs/admin-console.ts": (
        'import { svg } from "../svg";\n\nconst AdminConsoleLogo = svg`\n{svg}\n`;\n\nexport default AdminConsoleLogo;\n'
    ),
    "libs/assets/src/svg/svgs/secrets-manager.ts": (
        'import { svg } from "../svg";\n\nconst SecretsManagerLogo = svg`\n{svg}\n`;\n\nexport default SecretsManagerLogo;\n'
    ),
    "libs/assets/src/svg/svgs/secrets-manager-alt.ts": (
        'import { svg } from "../svg";\n\nexport const SecretsManagerAlt = svg`\n{svg}\n`;\n'
    ),
    "libs/assets/src/svg/svgs/provider-portal.ts": (
        'import { svg } from "../svg";\n\nconst ProviderPortalLogo = svg`\n{svg}\n`;\n\nexport default ProviderPortalLogo;\n'
    ),
    "libs/assets/src/svg/svgs/business-unit-portal.ts": (
        'import { svg } from "../svg";\n\nconst BusinessUnitPortalLogo = svg`\n{svg}\n`;\n\nexport default BusinessUnitPortalLogo;\n'
    ),
    "libs/assets/src/svg/svgs/bitwarden-logo.icon.ts": (
        'import { svg } from "../svg";\n\nexport const BitwardenLogo = svg`\n{svg}\n`;\n'
    ),
    "libs/assets/src/svg/svgs/bitwarden-logo-beta.icon.ts": (
        'import { svg } from "../svg";\n\nexport const BitwardenLogoBeta = svg`\n{svg}\n`;\n'
    ),
    "libs/assets/src/svg/svgs/shield.ts": (
        'import { svg } from "../svg";\n\nconst BitwardenShield = svg`\n{svg}\n`;\n\nexport { BitwardenShield };\n'
    ),
    "libs/assets/src/svg/svgs/bitwarden-icon.ts": (
        'import { svg } from "../svg";\n\nexport const BitwardenIcon = svg`\n{svg}\n`;\n'
    ),
}


def _lockup_svg():
    text = open(os.path.join(KIT, "05-wordmark-lockups", "komboe-lockup-horizontal-navy.svg"), encoding="utf-8").read()
    text = re.sub(r"<rect\b[^>]*/>", "", text)
    text = text.replace('fill="#F0ECE7"', 'class="tw-fill-fg-nav"')
    text = text.replace('fill="#0B1B33"', 'class="tw-fill-fg-nav"')
    text = text.replace('fill="#070702"', 'class="tw-fill-fg-nav"')
    return text.strip()


def _mark_icon_svg():
    mark = open(os.path.join(KIT, "01-master", "komboe-mark-mono-black.svg"), encoding="utf-8").read()
    mark = mark.replace('fill="#070702"', 'class="tw-fill-fg-nav"')
    mark = mark.replace('fill="#0B1B33"', 'class="tw-fill-fg-nav"')
    inner = re.search(r"<svg[^>]*>(.*)</svg>", mark, re.S)
    body = inner.group(1).strip() if inner else mark
    return (
        '<svg width="20" height="20" viewBox="0 0 1024 1024" fill="none" xmlns="http://www.w3.org/2000/svg">'
        f"{body}</svg>"
    )


def _file_icon_svg():
    """Neutral import glyph. Not a product mark."""
    return (
        '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">'
        '<path class="tw-fill-fg-nav" fill-rule="evenodd" d="M6 2.5h7.2L18 7.3V21.5H6V2.5Zm7 1.6V8h3.9L13 4.1ZM8.2 11.2h7.6V12.7H8.2v-1.5Zm0 3h7.6v1.5H8.2v-1.5Z"/>'
        "</svg>"
    )


def _remember_replaced(old_blobs):
    """Record sha256 of upstream bytes that this pass is about to overwrite."""
    deny_path = os.path.join(ROOT, "scripts", "branding_denylist.json")
    data = json.loads(open(deny_path, encoding="utf-8").read())
    hashes = set(data["sha256"])
    sigs = list(data.get("shield_paths") or [])
    for frag in UPSTREAM_SHIELD_FRAGMENTS:
        if frag not in sigs:
            sigs.append(frag)
    for blob in old_blobs:
        hashes.add(hashlib.sha256(blob).hexdigest())
    data["sha256"] = sorted(hashes)
    data["shield_paths"] = sigs
    data["note"] = (
        "Hashes of upstream Bitwarden artwork, including the illustrations and shared "
        "wordmark SVGs still byte-identical after the first rebrand. Import-format labels are not images."
    )
    open(deny_path, "w", encoding="utf-8").write(json.dumps(data, indent=2) + "\n")


def _illustration_paths():
    patterns = (
        "apps/*/src/images/new-experience/new-experience.*.png",
        "apps/web/src/images/welcome-dialog-graphic.png",
        "apps/web/src/images/sm-give-access.png",
        "apps/browser/src/images/at-risk-password-carousel/*.png",
    )
    found = []
    for pattern in patterns:
        found.extend(glob.glob(os.path.join(CLIENTS, pattern)))
    return found


def replace_leftover_branding():
    """Illustrations and shared wordmarks the first artwork pass did not touch."""
    require_pil()
    Image, _ = require_pil()
    changed = []
    old_blobs = []

    def stage(path, new):
        if isinstance(new, str):
            new = new.encode("utf-8")
        old = open(path, "rb").read() if os.path.isfile(path) else b""
        if old == new:
            return
        if old:
            old_blobs.append(old)
        if _write_bytes(path, new):
            changed.append(os.path.relpath(path, ROOT))

    for path in _illustration_paths():
        dark = ".dark." in os.path.basename(path)
        size = Image.open(path).size
        buf = io.BytesIO()
        plate(size, dark=dark).save(buf, "PNG", optimize=True)
        stage(path, buf.getvalue())
    lockup = _lockup_svg()
    mark = _mark_icon_svg()
    for rel, template in LOCKUP_ICONS.items():
        path = os.path.join(CLIENTS, rel)
        svg = mark if rel.endswith("bitwarden-icon.ts") else lockup
        stage(path, template.replace("{svg}", svg))
    import_path = os.path.join(CLIENTS, "libs/assets/src/svg/svgs/import-bitwarden.icon.ts")
    import_ts = (
        'import { svg } from "../svg";\n\nexport const ImportBitwardenIcon = svg`\n'
        + _file_icon_svg()
        + "\n`;\n"
    )
    stage(import_path, import_ts)
    if old_blobs:
        _remember_replaced(old_blobs)
    leftover = []
    for dirpath, _, filenames in os.walk(os.path.join(CLIENTS, "libs", "assets")):
        for name in filenames:
            path = os.path.join(dirpath, name)
            if not name.endswith((".ts", ".svg")) or os.path.getsize(path) > 5_000_000:
                continue
            blob = open(path, "rb").read()
            if any(frag.encode("ascii") in blob for frag in UPSTREAM_SHIELD_FRAGMENTS):
                leftover.append(os.path.relpath(path, ROOT))
    if leftover:
        sys.exit("upstream shield still in:\n" + "\n".join(leftover))
    locale_roots = (
        "apps/web/src/locales",
        "apps/browser/src/_locales",
        "apps/desktop/src/locales",
        "apps/cli/src/locales",
    )
    for rel in locale_roots:
        for path in glob.glob(os.path.join(CLIENTS, rel, "*", "messages.json")):
            text = open(path, encoding="utf-8").read()
            updated = rewrite_locale(text)
            if updated != text:
                _write_text(path, updated)
                changed.append(os.path.relpath(path, ROOT))
    return changed


def apply_client_artwork(changed: list | None = None):
    """Replace desktop, extension, web, and shared images the earlier rebrand pass skipped."""
    require_pil()
    changed = changed if changed is not None else []
    C = CLIENTS
    ico = os.path.join(KIT, "09-desktop", "electron", "icon.ico")
    icon1024 = os.path.join(KIT, "09-desktop", "electron", "icon-1024.png")
    mark_navy = os.path.join(KIT, "01-master", "komboe-mark-navy.png")
    mark_black = os.path.join(KIT, "01-master", "komboe-mark-mono-black.png")
    mark_white = os.path.join(KIT, "01-master", "komboe-mark-mono-white.png")

    def note(path, wrote):
        if wrote:
            changed.append(os.path.relpath(path, ROOT))

    def raster(dest, im):
        note(dest, replace_raster(dest, im))

    def from_file(dest, src, bg=None):
        Image, _ = require_pil()
        size = Image.open(dest).size if os.path.exists(dest) else Image.open(src).size
        raster(dest, _png(src, size, bg))

    # Desktop tray, window, and notification icons live under src/images, not resources/.
    images = os.path.join(C, "apps/desktop/src/images")
    for name in ("icon.ico", "icon_beta.ico"):
        note(os.path.join(images, name), copy_ico(ico, os.path.join(images, name)))
    for name in ("icon.png", "icon_beta.png", "icon_dev.png"):
        from_file(os.path.join(images, name), icon1024)
    for name in ("icon-template.png", "icon-template@2x.png"):
        from_file(os.path.join(images, name), mark_black)
    for name in ("icon-highlight.png", "icon-highlight@2x.png"):
        from_file(os.path.join(images, name), mark_white)
    for name, variant in (("logo-dark@2x.png", "navy"), ("logo-white@2x.png", "mono-white")):
        dest = os.path.join(images, name)
        from_file(dest, os.path.join(KIT, "05-wordmark-lockups", f"komboe-lockup-horizontal-{variant}.png"))

    resources = os.path.join(C, "apps/desktop/resources")
    for name in ("icon.ico", "icon.beta.ico"):
        note(os.path.join(resources, name), copy_ico(ico, os.path.join(resources, name)))
    note(os.path.join(resources, "installerSidebar.bmp"), sidebar_bmp(os.path.join(resources, "installerSidebar.bmp")))
    tiles = os.path.join(KIT, "09-desktop", "windows", "tiles")
    appx = os.path.join(resources, "appx")
    if os.path.isdir(appx):
        for name in os.listdir(appx):
            src = os.path.join(tiles, name)
            dest = os.path.join(appx, name)
            if os.path.isfile(src):
                from_file(dest, src)
            elif name.lower().endswith(".png"):
                from_file(dest, icon1024, NAVY)

    note(
        os.path.join(C, "apps/desktop/macos/autofill-extension/bitwarden-icon.png"),
        fit_file(icon1024, os.path.join(C, "apps/desktop/macos/autofill-extension/bitwarden-icon.png")),
    )

    # Extension popup wordmarks, Safari icon set, store icons, Windows tiles, store screenshots.
    popup = os.path.join(C, "apps/browser/src/popup/images")
    for name, variant in (("logo-dark@2x.png", "navy"), ("logo-white@2x.png", "mono-white")):
        from_file(os.path.join(popup, name), os.path.join(KIT, "05-wordmark-lockups", f"komboe-lockup-horizontal-{variant}.png"))
    safari = os.path.join(C, "apps/browser/src/safari")
    for path in glob.glob(safari + "/**/*.png", recursive=True):
        from_file(path, icon1024)
    store = os.path.join(C, "apps/browser/store")
    for path in glob.glob(store + "/**/*.png", recursive=True):
        base = os.path.basename(path).lower()
        if "screenshot" in path.replace("\\", "/") or "promo" in base or base.startswith(("chrome0", "firefox", "edge", "opera")):
            Image, _ = require_pil()
            raster(path, plate(Image.open(path).size, dark=True))
        else:
            from_file(path, icon1024, NAVY)
    desktop_store = os.path.join(C, "apps/desktop/stores")
    for path in glob.glob(desktop_store + "/**/*.png", recursive=True):
        Image, _ = require_pil()
        raster(path, plate(Image.open(path).size, dark=True))

    # Web register lockup and the vertical Bitwarden mark used as our own logo.
    reg = os.path.join(C, "apps/web/src/images/register-layout")
    note(os.path.join(reg, "logo-horizontal-white.svg"), replace_svg(
        os.path.join(reg, "logo-horizontal-white.svg"),
        os.path.join(KIT, "05-wordmark-lockups", "komboe-lockup-horizontal-mono-white.svg"),
    ))
    from_file(
        os.path.join(reg, "logo-horizontal-white.png"),
        os.path.join(KIT, "05-wordmark-lockups", "komboe-lockup-horizontal-mono-white.png"),
    )
    note(
        os.path.join(C, "apps/web/src/images/integrations/bitwarden-vertical-blue.svg"),
        replace_svg(
            os.path.join(C, "apps/web/src/images/integrations/bitwarden-vertical-blue.svg"),
            os.path.join(KIT, "05-wordmark-lockups", "komboe-lockup-stacked-navy.svg"),
        ),
    )
    for name, variant in (
        ("logo-dark@2x.png", "navy"),
        ("logo-primary@2x.png", "navy"),
        ("logo-white@2x.png", "mono-white"),
    ):
        dest = os.path.join(C, "apps/web/src/images", name)
        if os.path.exists(dest):
            from_file(dest, os.path.join(KIT, "05-wordmark-lockups", f"komboe-lockup-horizontal-{variant}.png"))

    # Favicons must stay byte-identical to the kit. The earlier PNG pass resizes a master
    # and would otherwise replace these.
    for dest_rel, src_rel in (
        ("apps/web/src/favicon.ico", "favicons/favicon.ico"),
        ("apps/web/src/images/icons/favicon-32x32.png", "favicons/favicon-32x32.png"),
        ("apps/web/src/images/icons/favicon-16x16.png", "favicons/favicon-16x16.png"),
        ("apps/web/src/images/icons/favicon.svg", "favicons/favicon.svg"),
        ("apps/web/src/images/icons/android-chrome-192x192.png", "favicons/android-chrome-192x192.png"),
        ("apps/web/src/images/icons/android-chrome-512x512.png", "favicons/android-chrome-512x512.png"),
        ("apps/web/src/images/icons/apple-touch-icon.png", "favicons/apple-touch-icon.png"),
        ("apps/web/src/images/icons/maskable-icon-512x512.png", "favicons/maskable-icon-512x512.png"),
    ):
        dest = os.path.join(C, dest_rel)
        src = os.path.join(KIT, src_rel)
        if os.path.exists(src):
            note(dest, _write_bytes(dest, open(src, "rb").read()))

    shield = os.path.join(C, "libs/assets/src/material-icons/bitwarden-shield.svg")
    note(shield, shield_svg(shield))
    replace_bwi_shield(os.path.join(C, "libs/angular/src/scss/bwicons/fonts"))
    changed.append("clients/upstream/libs/angular/src/scss/bwicons/fonts/bwi-font.*")
    changed.extend(replace_leftover_branding())
    return changed


def _svg_transform(text: str):
    from fontTools.misc.transform import Transform

    tf = Transform()
    for kind, args in re.findall(r"(translate|scale)\(([^)]*)\)", text):
        nums = [float(x) for x in re.split(r"[\s,]+", args.strip()) if x]
        if kind == "translate":
            tf = tf.translate(nums[0], nums[1] if len(nums) > 1 else 0)
        else:
            sx = nums[0]
            sy = nums[1] if len(nums) > 1 else sx
            tf = tf.scale(sx, sy)
    return tf


def _bake_path(d: str, transform: str | None) -> str:
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.svgLib.path import parse_path

    pen = SVGPathPen(None)
    target = pen
    if transform:
        target = TransformPen(pen, _svg_transform(transform))
    parse_path(d, target)
    return pen.getCommands()


def android_vector_from_svg(svg_path, fill):
    """Official kit SVG as an Android vector. Transforms are baked into pathData."""
    text = open(svg_path, encoding="utf-8").read()
    vb = re.search(r'viewBox="([^"]+)"', text)
    _, _, w, h = (float(x) for x in vb.group(1).split()) if vb else (0, 0, 1024, 1024)
    parts = []
    for m in re.finditer(r"<path\b([^>]*)/?>", text):
        attrs = m.group(1)
        d = re.search(r'd="([^"]+)"', attrs)
        if not d:
            continue
        tr = re.search(r'transform="([^"]+)"', attrs)
        baked = _bake_path(d.group(1), tr.group(1) if tr else None)
        parts.append(
            f'  <path android:fillColor="{fill}" android:fillType="evenOdd" android:pathData="{baked}"/>'
        )
    if not parts:
        sys.exit(f"no paths in {svg_path}")
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<vector xmlns:android="http://schemas.android.com/apk/res/android" '
        f'android:width="{max(1, round(w / 10))}dp" android:height="{max(1, round(h / 10))}dp" '
        f'android:viewportWidth="{w:.4g}" android:viewportHeight="{h:.4g}">\n'
        + "\n".join(parts) + "\n</vector>\n"
    )


def android_gif(dest, dark=False):
    Image, _ = require_pil()
    size = (480, 270)
    if os.path.exists(dest):
        try:
            size = Image.open(dest).size
        except Exception:
            pass
    frames = []
    for scale in (0.92, 0.96, 1.0, 0.96):
        canvas = Image.new("RGBA", size, NAVY if dark else OFFWHITE)
        side = int(min(size) * 0.55 * scale)
        mark = mark_png((side, side), "mono-white" if dark else "navy")
        canvas.paste(mark, ((size[0] - side) // 2, (size[1] - side) // 2), mark)
        frames.append(canvas.convert("P", palette=Image.Palette.ADAPTIVE))
    buf = io.BytesIO()
    frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:], duration=180, loop=0, disposal=2)
    return _write_bytes(dest, buf.getvalue())
